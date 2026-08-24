const fs = require('fs');
const d = JSON.parse(fs.readFileSync('/home/cahyo/trading-bot/ajaib/session/storage-state.json', 'utf8'));
console.log('All cookies:');
d.cookies.forEach(c => console.log(`  ${c.name} = ${c.value.substring(0, 30)} (domain: ${c.domain}, httpOnly: ${c.httpOnly})`));
