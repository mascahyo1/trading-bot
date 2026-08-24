#!/usr/bin/env node
/**
 * Simple SOCKS5 proxy server for Windows
 * Usage: node socks-proxy.js [port]
 * 
 * Browser on VPS connects to this proxy
 * Traffic exits through this machine's internet
 */

const net = require('net');

const PORT = parseInt(process.argv[2]) || 1080;

const server = net.createServer((socket) => {
    socket.once('data', (data) => {
        // SOCKS5 handshake
        if (data[0] !== 0x05) {
            socket.end();
            return;
        }

        // Accept no auth
        socket.write(Buffer.from([0x05, 0x00]));

        socket.once('data', (data) => {
            const cmd = data[1];
            const atyp = data[3];

            let targetHost, targetPort;

            if (atyp === 0x01) {
                // IPv4
                targetHost = `${data[4]}.${data[5]}.${data[6]}.${data[7]}`;
                targetPort = data.readUInt16BE(8);
            } else if (atyp === 0x03) {
                // Domain
                const len = data[4];
                targetHost = data.slice(5, 5 + len).toString();
                targetPort = data.readUInt16BE(5 + len);
            } else if (atyp === 0x04) {
                // IPv6 - not supported
                socket.end();
                return;
            }

            const target = net.connect(targetPort, targetHost);
            target.on('connect', () => {
                socket.write(Buffer.from([0x05, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]));
                socket.pipe(target);
                target.pipe(socket);
            });

            target.on('error', () => {
                socket.end();
            });
        });
    });

    socket.on('error', () => {});
});

server.listen(PORT, '0.0.0.0', () => {
    console.log(`SOCKS5 proxy running on port ${PORT}`);
    console.log(`VPS browser should connect to: socks5://<your-ip>:${PORT}`);
});

server.on('error', (err) => {
    console.error('Server error:', err.message);
});
