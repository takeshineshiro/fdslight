#!/usr/bin/env python3
"""
隧道客户端基本类
"""
import socket, sys, time
import fdslight_etc.fn_gw as fngw_config
import pywind.evtframework.handler.udp_handler as udp_handler
import freenet.lib.base_proto.tunnel_udp as tunnel_proto
import freenet.handler.traffic_pass as traffic_pass
import freenet.lib.fdsl_ctl as fdsl_ctl
import freenet.lib.base_proto.utils as proto_utils
import freenet.lib.utils as utils


class tunnelc_udp(udp_handler.udp_handler):
    __server = None

    __traffic_fetch_fd = -1
    __traffic_send_fd = -2
    __traffic6_send_fd = -2

    __dns_fd = -1

    __encrypt_m = None
    __decrypt_m = None

    __session_id = None

    __debug = False

    # 服务端IP地址
    __server_ipaddr = None

    __LOOP_TIMEOUT = 10

    __conn_time = 0
    __conn_timeout = 0

    def init_func(self, creator_fd, session_id, dns_fd, raw_socket_fd, raw6_socket_fd, debug=False, is_ipv6=False):
        self.__server = fngw_config.configs["udp_server_address"]

        name = "freenet.lib.crypto.%s" % fngw_config.configs["udp_crypto_module"]["name"]
        __import__(name)
        m = sys.modules.get(name, None)

        crypto_config = fngw_config.configs["udp_crypto_module"]["configs"]

        self.__encrypt_m = m.encrypt()
        self.__decrypt_m = m.decrypt()

        self.__encrypt_m.config(crypto_config)
        self.__decrypt_m.config(crypto_config)

        self.__debug = debug

        self.__session_id = session_id

        self.__traffic_send_fd = raw_socket_fd
        self.__traffic6_send_fd = raw6_socket_fd
        self.__conn_timeout = int(fngw_config.configs["timeout"])

        if is_ipv6:
            s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.set_socket(s)
        self.__dns_fd = dns_fd
        self.dispatcher.bind_session_id(self.__session_id, self.fileno, "udp")

        try:
            self.connect(self.__server)
        except socket.gaierror:
            self.close()
            return -1

        ipaddr, _ = s.getpeername()

        self.__server_ipaddr = ipaddr

        self.__init()
        self.__conn_time = time.time()
        self.register(self.fileno)
        self.add_evt_read(self.fileno)

        account = fngw_config.configs["account"]
        self.__session_id = proto_utils.gen_session_id(account["username"], account["password"])
        self.set_timeout(self.fileno, self.__LOOP_TIMEOUT)

        return self.fileno

    def __init(self):
        if not fngw_config.configs["udp_global"]: return
        self.__traffic_fetch_fd = self.create_handler(self.fileno, traffic_pass.traffic_read)
        n = utils.ip4s_2_number(self.__server_ipaddr)

        subnet, prefix = fngw_config.configs["udp_proxy_subnet"]
        subnet = utils.ip4b_2_number(socket.inet_aton(subnet))

        fdsl_ctl.set_udp_proxy_subnet(self.__traffic_fetch_fd, subnet, chr(int(prefix)).encode())
        fdsl_ctl.set_tunnel(self.__traffic_fetch_fd, n)

        return

    def __handle_data_from_tunnel(self, byte_data):
        try:
            length = (byte_data[2] << 8) | byte_data[3]
        except IndexError:
            return
        if length > 1500:
            self.print_access_log("error_pkt_length:%s,real_length:%s" % (length, len(byte_data),))
            return
        if length != len(byte_data):
            self.print_access_log("error_length_not_match:%s,real_length:%s" % (length, len(byte_data),))
            return
        byte_data = byte_data[0:length]
        p = byte_data[9]

        # print("recv:",byte_data)
        # 过滤到不支持的协议

        if p not in (1, 6, 17,): return
        #tun_fd = self.dispatcher.get_tun()
        self.send_message_to_handler(self.fileno, self.__traffic_send_fd, byte_data)
        return

    def __send_data(self, byte_data, action=tunnel_proto.ACT_DATA):
        # if self.__debug: self.print_access_log("send_data")
        self.__conn_time = time.time()
        try:
            ippkts = self.__encrypt_m.build_packets(self.__session_id, action, byte_data)
            self.__encrypt_m.reset()
        except ValueError:
            return
        # print("send:", byte_data)
        for ippkt in ippkts: self.send(ippkt)

        self.add_evt_write(self.fileno)

    def udp_readable(self, message, address):
        result = self.__decrypt_m.parse(message)
        if not result: return

        session_id, action, byte_data = result
        if session_id != self.__session_id: return

        if action not in tunnel_proto.ACTS:
            self.print_access_log("can_not_found_action_%s" % action)
            return

        if action == tunnel_proto.ACT_DATA: self.__handle_data_from_tunnel(byte_data)
        if action == tunnel_proto.ACT_DNS: self.send_message_to_handler(self.fileno, self.__dns_fd, byte_data)

    def udp_writable(self):
        self.remove_evt_write(self.fileno)

    def udp_error(self):
        self.print_access_log("server_down")
        self.delete_handler(self.fileno)

    def udp_timeout(self):
        if time.time() - self.__conn_time > self.__conn_timeout:
            self.delete_handler(self.fileno)
            return
        self.set_timeout(self.fileno, self.__LOOP_TIMEOUT)

    def udp_delete(self):
        self.dispatcher.unbind_session_id(self.__session_id)
        self.unregister(self.fileno)
        if fngw_config.configs["udp_global"]:
            self.delete_handler(self.__traffic_fetch_fd)
        self.socket.close()

    @property
    def encrypt(self):
        return self.__encrypt_m

    @property
    def decrypt(self):
        return self.__decrypt_m

    def __udp_local_proxy_for_send(self, byte_data):
        self.dispatcher.send_msg_to_udp_proxy(self.__session_id, byte_data)

    def __handle_ipv4_traffic_from_lan(self, byte_data):
        protocol = byte_data[9]
        if protocol not in (1, 6, 17,): return

        ipaddr = socket.inet_ntoa(byte_data[16:20])
        self.dispatcher.update_router_access_time(ipaddr)
        self.__send_data(byte_data)

    def __handle_ipv6_traffic_from_lan(self, byte_data):
        pass

    def __handle_traffic_from_lan(self, byte_data):
        size = len(byte_data)
        if size < 21: return
        version = (byte_data[0] & 0xf0) >> 4
        if version not in (4, 6,): return
        if version == 4: self.__handle_ipv4_traffic_from_lan(byte_data)
        if version == 6: self.__handle_ipv6_traffic_from_lan(byte_data)

    def message_from_handler(self, from_fd, byte_data):
        self.__handle_traffic_from_lan(byte_data)

    def print_access_log(self, text):
        t = time.strftime("%Y-%m-%d %H:%M:%S")
        addr = "%s:%s" % self.__server
        echo = "%s        %s         %s" % (text, addr, t)

        print(echo)
        sys.stdout.flush()

    def handler_ctl(self, from_fd, cmd, *args, **kwargs):
        if cmd not in ("request_dns",): return False
        dns_msg, = args
        self.__send_data(dns_msg, action=tunnel_proto.ACT_DNS)
        return True
