const fs = require('fs');
const d = JSON.parse(fs.readFileSync('/home/cahyo/trading-bot/ajaib/session/storage-state.json', 'utf8'));
console.log('Cookies:', d.cookies.length);
const at = d.cookies.find(c => c.name === 'access_token');
console.log('access_token:', at ? at.value.substring(0, 50) + '...' : 'NOT FOUND');
const rt = d.cookies.find(c => c.name === 'refresh_token');
console.log('refresh_token:', rt ? rt.value.substring(0, 50) + '...' : 'NOT FOUND');
