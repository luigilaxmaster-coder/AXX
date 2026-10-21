const { execSync } = require('child_process');

try {
    const output = execSync('powershell -Command "Get-CimInstance Win32_Process -Filter \\"Name LIKE \'python%\'\\" | Select-Object -Property ProcessId, CommandLine | ConvertTo-Json"', { encoding: 'utf8' });
    const data = JSON.parse(output || '[]');
    const list = Array.isArray(data) ? data : (data ? [data] : []);
    const zombies = list.filter(p => p.CommandLine && p.CommandLine.includes('backend.connect.mcp_server'));
    console.log('Total python processes:', list.length);
    console.log('Zombie MCP server processes:', zombies.length);
    if (zombies.length > 0) {
        console.log('Zombies found:', zombies);
    }
} catch (err) {
    console.log('Error querying processes:', err.message);
}
