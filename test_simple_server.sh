#!/bin/bash
cd puppeteer-server
echo "Starting Puppeteer server..."
node server.js &
SERVER_PID=$!

sleep 5

echo "Checking server status..."
curl http://localhost:3000/status

echo -e "\n\nKilling server..."
kill $SERVER_PID