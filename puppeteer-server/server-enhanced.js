const puppeteer = require('puppeteer');
const express = require('express');
const WebSocket = require('ws');
const app = express();

let browser;
let browserWSEndpoint;
const pages = new Map(); // Track active pages

// WebSocket server for real-time monitoring
const wss = new WebSocket.Server({ port: 3001 });

// Broadcast to all connected clients
function broadcast(data) {
  wss.clients.forEach(client => {
    if (client.readyState === WebSocket.OPEN) {
      client.send(JSON.stringify(data));
    }
  });
}

// Start Puppeteer browser with CDP enabled
async function startBrowser() {
  try {
    browser = await puppeteer.launch({
      headless: false,
      args: [
        '--remote-debugging-port=9222',
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-blink-features=AutomationControlled',
        // Performance optimizations for screenshots
        '--disable-gpu-sandbox',
        '--disable-software-rasterizer',
        '--disable-dev-shm-usage'
      ],
      defaultViewport: null // Use full window size
    });
    
    browserWSEndpoint = browser.wsEndpoint();
    console.log('Browser started with WebSocket endpoint:', browserWSEndpoint);
    
    // Monitor browser events
    browser.on('targetcreated', async (target) => {
      if (target.type() === 'page') {
        const page = await target.page();
        if (page) {
          const pageId = target._targetId;
          pages.set(pageId, page);
          
          // Set up page monitoring
          setupPageMonitoring(page, pageId);
          
          broadcast({
            type: 'page_created',
            pageId,
            url: page.url(),
            timestamp: new Date().toISOString()
          });
        }
      }
    });
    
    browser.on('targetdestroyed', (target) => {
      const pageId = target._targetId;
      pages.delete(pageId);
      broadcast({
        type: 'page_closed',
        pageId,
        timestamp: new Date().toISOString()
      });
    });
    
    return {
      wsEndpoint: browserWSEndpoint,
      cdpUrl: 'http://localhost:9222'
    };
  } catch (error) {
    console.error('Failed to start browser:', error);
    throw error;
  }
}

// Set up monitoring for a page
function setupPageMonitoring(page, pageId) {
  // Monitor navigation
  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame()) {
      broadcast({
        type: 'navigation',
        pageId,
        url: frame.url(),
        timestamp: new Date().toISOString()
      });
    }
  });
  
  // Monitor console logs
  page.on('console', (msg) => {
    broadcast({
      type: 'console',
      pageId,
      level: msg.type(),
      text: msg.text(),
      timestamp: new Date().toISOString()
    });
  });
  
  // Monitor page errors
  page.on('pageerror', (error) => {
    broadcast({
      type: 'page_error',
      pageId,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  });
}

// API endpoints
app.use(express.json());

app.get('/status', (req, res) => {
  res.json({
    status: browser ? 'running' : 'stopped',
    wsEndpoint: browserWSEndpoint,
    cdpUrl: 'http://localhost:9222',
    activePagesCount: pages.size,
    monitoring: {
      websocket: 'ws://localhost:3001',
      connectedClients: wss.clients.size
    }
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
      pages.clear();
      res.json({ message: 'Browser stopped' });
    } else {
      res.json({ message: 'Browser not running' });
    }
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Screenshot endpoint for testing
app.get('/screenshot/:pageId?', async (req, res) => {
  try {
    let page;
    
    if (req.params.pageId) {
      page = pages.get(req.params.pageId);
    } else {
      // Get first available page
      page = pages.values().next().value;
    }
    
    if (!page) {
      return res.status(404).json({ error: 'No page found' });
    }
    
    const screenshot = await page.screenshot({ 
      encoding: 'base64',
      fullPage: true 
    });
    
    res.json({
      screenshot,
      pageId: req.params.pageId || 'first',
      url: page.url(),
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// WebSocket connection handling
wss.on('connection', (ws) => {
  console.log('New WebSocket client connected');
  
  // Send initial status
  ws.send(JSON.stringify({
    type: 'connected',
    status: browser ? 'running' : 'stopped',
    activePagesCount: pages.size,
    timestamp: new Date().toISOString()
  }));
  
  ws.on('close', () => {
    console.log('WebSocket client disconnected');
  });
});

// Start server
const PORT = process.env.PORT || 3000;
app.listen(PORT, async () => {
  console.log(`Enhanced Puppeteer server running on port ${PORT}`);
  console.log(`WebSocket monitoring on port 3001`);
  
  // Auto-start browser on server start
  try {
    await startBrowser();
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
  wss.close();
  process.exit(0);
});