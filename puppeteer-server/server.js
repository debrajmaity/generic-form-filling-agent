const puppeteer = require('puppeteer');
const express = require('express');
const app = express();

// Middleware
app.use(express.json());

let browser;
let browserWSEndpoint;

// Start Puppeteer browser with CDP enabled
async function startBrowser() {
  try {
    const cdpPort = process.env.CDP_PORT || 9222;
    const headless = process.env.HEADLESS === 'true';
    
    console.log(`Starting browser with CDP port: ${cdpPort}, headless: ${headless}`);
    
    browser = await puppeteer.launch({
      headless: headless,
      args: [
        `--remote-debugging-port=${cdpPort}`,
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-blink-features=AutomationControlled',
        '--disable-gpu',
        '--disable-dev-shm-usage'
      ],
      dumpio: true  // Show browser console output
    });
    
    browserWSEndpoint = browser.wsEndpoint();
    console.log('Browser started with WebSocket endpoint:', browserWSEndpoint);
    
    // Return browser info
    return {
      wsEndpoint: browserWSEndpoint,
      cdpUrl: `http://localhost:${cdpPort}`
    };
  } catch (error) {
    console.error('Failed to start browser:', error);
    throw error;
  }
}

// API endpoints
app.get('/status', (req, res) => {
  res.json({
    status: browser ? 'running' : 'stopped',
    wsEndpoint: browserWSEndpoint,
    cdpUrl: 'http://localhost:9222'
  });
});

app.post('/browser/start', async (req, res) => {
  try {
    if (browser) {
      res.json({ 
        message: 'Browser already running',
        wsEndpoint: browserWSEndpoint,
        cdpUrl: 'http://localhost:9222'
      });
    } else {
      const info = await startBrowser();
      res.json({ 
        message: 'Browser started',
        ...info
      });
    }
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/browser/stop', async (req, res) => {
  try {
    if (browser) {
      await browser.close();
      browser = null;
      browserWSEndpoint = null;
      res.json({ message: 'Browser stopped' });
    } else {
      res.json({ message: 'Browser not running' });
    }
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Start server
const PORT = process.env.PORT || 3000;
app.listen(PORT, async () => {
  console.log(`Puppeteer server running on port ${PORT}`);
  
  // Auto-start browser on server start
  try {
    console.log('Attempting to auto-start browser...');
    const browserInfo = await startBrowser();
    console.log('Browser auto-started successfully:', browserInfo);
  } catch (error) {
    console.error('Failed to auto-start browser:', error);
  }
});

// Graceful shutdown
process.on('SIGINT', async () => {
  console.log('Shutting down...');
  if (browser) {
    await browser.close();
  }
  process.exit(0);
});