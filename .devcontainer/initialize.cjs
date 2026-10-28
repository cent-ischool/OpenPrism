const fs = require('node:fs');

if (!fs.existsSync('.env')) {
  fs.copyFileSync('.env.sample', '.env');
}