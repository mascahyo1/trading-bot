const fs = require('fs');
const https = require('https');
const http = require('http');

const cookieStr = fs.readFileSync('session/cookies.txt', 'utf8');
const cookies = cookieStr.split('; ').reduce((acc, c) => {
    const [name, ...rest] = c.split('=');
    acc[name] = rest.join('=');
    return acc;
}, {});

const token = cookies['access_token'];
console.log('Access token found:', token ? token.substring(0, 50) + '...' : 'NOT FOUND');

// Try different API endpoints
const endpoints = [
    'https://api.ajaib.co.id/api/v2/portfolio',
    'https://api.ajaib.co.id/api/v2/account',
    'https://api.ajaib.co.id/api/v2/assets',
    'https://api.ajaib.co.id/api/portfolio',
    'https://invest.ajaib.co.id/api/v2/portfolio',
    'https://invest.ajaib.co.id/api/v2/account',
];

function tryEndpoint(url, token) {
    return new Promise((resolve, reject) => {
        const mod = url.startsWith('https') ? https : http;
        const req = mod.get(url, {
            headers: {
                'Authorization': 'Bearer ' + token,
                'Cookie': cookieStr,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
            },
        }, (res) => {
            let body = '';
            res.on('data', chunk => body += chunk);
            res.on('end', () => {
                console.log(`\n=== ${url} ===`);
                console.log('Status:', res.statusCode);
                console.log('Body (first 500):', body.substring(0, 500));
                resolve();
            });
        });
        req.on('error', (e) => {
            console.log(`\n=== ${url} ===`);
            console.log('Error:', e.message);
            resolve();
        });
        req.setTimeout(10000, () => {
            console.log(`\n=== ${url} ===`);
            console.log('Timeout');
            req.destroy();
            resolve();
        });
    });
}

(async () => {
    for (const url of endpoints) {
        await tryEndpoint(url, token);
    }
})();
