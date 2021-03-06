#!/usr/bin/env python3
import pywind.evtframework.handler.handler as handler
import pywind.lib.reader as reader
import pywind.lib.writer as writer


class tcp_handler(handler.handler):
    __reader = None
    __writer = None
    __socket = None

    # 作为客户端连接是否成功
    __conn_ok = False
    # 作为客户端的连接事件标记,用以表示是否连接成功
    __conn_ev_flag = 0
    __is_async_socket_client = False
    __is_listen_socket = False
    __delete_this_no_sent_data = False

    def __init__(self):
        super(tcp_handler, self).__init__()
        self.__reader = reader.reader()
        self.__writer = writer.writer()

    def init_func(self, creator_fd, *args, **kwargs):
        """
        :param creator_fd:
        :param args:
        :param kwargs:
        :return fileno:
        """
        pass

    def after(self, *args, **kwargs):
        """之后要做的事情,有用户自己的服务端程序调用,可能常常用于多进程
        """
        pass

    def set_socket(self, s):
        s.setblocking(0)
        self.set_fileno(s.fileno())
        self.__socket = s

    def accept(self):
        return self.socket.accept()

    def close(self):
        self.socket.close()

    @property
    def socket(self):
        return self.__socket

    def bind(self, address):
        self.socket.bind(address)

    def listen(self, backlog):
        self.__is_listen_socket = True
        self.socket.listen(backlog)

    @property
    def reader(self):
        return self.__reader

    @property
    def writer(self):
        return self.__writer

    def evt_read(self):
        if self.__is_listen_socket:
            self.tcp_accept()
            return

        if self.__is_async_socket_client and not self.is_conn_ok():
            self.__conn_ev_flag = 1
            return

        while 1:
            try:
                recv_data = self.socket.recv(4096)
                if not recv_data:
                    self.error()
                    break
                self.reader._putvalue(self.handle_tcp_received_data(recv_data))
            except BlockingIOError:
                self.tcp_readable()
                break
            except ConnectionResetError:
                self.error()
                break

            ''''''
        return

    def evt_write(self):
        if self.__is_async_socket_client and not self.is_conn_ok():
            self.unregister(self.fileno)
            if self.__conn_ev_flag:
                self.error()
                return
            ''''''
            self.__conn_ok = True
            self.connect_ok()
            return
        sent_data = self.writer._getvalue()
        if not sent_data: self.tcp_writable()
        try:
            sent_size = self.socket.send(sent_data)
            rest = sent_data[sent_size:]
            if rest:
                self.writer.write(rest)
                return
            if self.__delete_this_no_sent_data and self.writer.size() == 0:
                self.delete_handler(self.fileno)
                return
            self.tcp_writable()
        except ConnectionError:
            self.error()

    def timeout(self):
        if self.__is_async_socket_client and not self.is_conn_ok():
            self.unregister(self.fileno)

        self.tcp_timeout()

    def error(self):
        self.tcp_error()

    def delete(self):
        self.tcp_delete()

    def message_from_handler(self, from_fd, byte_data):
        """重写这个方法
        :param from_fd:
        :param args:
        :param kwargs:
        :return:
        """
        pass

    def reset(self):
        self.tcp_reset()

    def tcp_accept(self):
        """重写这个方法,接受客户端连接
        :return:
        """
        pass

    def tcp_readable(self):
        """重写这个方法
        :return:
        """
        pass

    def tcp_writable(self):
        """重写这个方法
        :return:
        """
        pass

    def tcp_timeout(self):
        """重写这个方法
        :return:
        """
        pass

    def tcp_error(self):
        """重写这个方法
        :return:
        """

    def tcp_delete(self):
        """重写这个方法
        :return:
        """
        pass

    def tcp_reset(self):
        pass

    def connect(self, address, timeout=3):
        self.__connect_addr = address
        self.__connect_timeout = timeout
        self.__is_async_socket_client = True
        err = self.socket.connect_ex(address)
        self.register(self.fileno)
        self.add_evt_read(self.fileno)
        self.add_evt_write(self.fileno)

        if err:
            self.set_timeout(self.fileno, timeout)
            return

        self.__conn_ok = True

    def connect_ok(self):
        """连接成功后调用的函数,重写这个方法
        :return:
        """
        pass

    def is_conn_ok(self):
        return self.__conn_ok

    def delete_this_no_sent_data(self):
        """没有可发送的数据时候删除这个handler"""
        self.__delete_this_no_sent_data = True

    def getpeername(self):
        return self.socket.getpeername()

    def handle_tcp_received_data(self, received_data):
        """处理刚刚接收过来的数据包,该函数在socket.recv调用之后被调用
        :param received_data:
        :return bytes:
        """
        return received_data
