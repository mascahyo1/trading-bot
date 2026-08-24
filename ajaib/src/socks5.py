#!/usr/bin/env python3
"""Simple SOCKS5 proxy server untuk VPS."""
import socket
import select
import struct
import threading
import sys

def handle_client(client):
    try:
        data = client.recv(262)
        if not data or data[0] != 0x05:
            client.close()
            return
        client.send(b'\x05\x00')
        data = client.recv(262)
        if not data or data[1] != 0x01:
            client.close()
            return
        atyp = data[3]
        if atyp == 0x01:
            target = socket.inet_ntoa(data[4:8])
            port = struct.unpack('!H', data[8:10])[0]
        elif atyp == 0x03:
            length = data[4]
            target = data[5:5+length].decode()
            port = struct.unpack('!H', data[5+length:5+length+2])[0]
        else:
            client.close()
            return
        remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        remote.connect((target, port))
        client.send(b'\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00')
        while True:
            r, _, _ = select.select([client, remote], [], [], 60)
            if not r:
                break
            for s in r:
                data = s.recv(4096)
                if not data:
                    client.close()
                    remote.close()
                    return
                if s is client:
                    remote.send(data)
                else:
                    client.send(data)
    except:
        pass
    finally:
        client.close()

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 1080
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('127.0.0.1', port))
    server.listen(100)
    print(f'SOCKS5 proxy listening on 127.0.0.1:{port}')
    while True:
        client, _ = server.accept()
        threading.Thread(target=handle_client, args=(client,), daemon=True).start()

if __name__ == '__main__':
    main()
