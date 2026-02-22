import puppeteer from 'puppeteer-core';

const BASE = 'http://127.0.0.1:3000';
const USERNAME = 'e2e_runner';
const PASSWORD = 'E2ePass!2026';
const CHROME = '/usr/bin/google-chrome';

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForPath(page, predicate, timeoutMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const current = new URL(page.url());
    if (predicate(current.pathname)) return;
    await sleep(200);
  }
  throw new Error(`Timed out waiting for URL, current=${page.url()}`);
}

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: 'new',
  args: [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--autoplay-policy=no-user-gesture-required',
  ],
  defaultViewport: { width: 1440, height: 900 },
});

const page = await browser.newPage();

try {
  page.on('console', (msg) => {
    const text = msg.text();
    if (text.includes('WebSocket') || text.includes('Session') || text.includes('WebRTC')) {
      console.log('[browser]', text);
    }
  });

  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2', timeout: 30000 });
  await page.type('input[type="text"]', USERNAME, { delay: 30 });
  await page.type('input[type="password"]', PASSWORD, { delay: 30 });
  await page.click('button[type="submit"]');

  await waitForPath(page, (pathname) => pathname === '/devices', 20000);
  await page.waitForSelector('button', { timeout: 10000 });

  const clicked = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const connect = buttons.find((b) => b.textContent?.trim() === 'Connect' && !(b).disabled);
    if (!connect) return false;
    connect.click();
    return true;
  });

  if (!clicked) {
    throw new Error('No enabled Connect button found on devices page');
  }

  await waitForPath(page, (pathname) => pathname.startsWith('/session/'), 20000);

  let last = null;
  let success = false;
  for (let i = 0; i < 90; i++) {
    const state = await page.evaluate(() => {
      const statusNode = Array.from(document.querySelectorAll('div')).find((d) => d.textContent?.includes('Status:'));
      const statusText = statusNode?.textContent?.trim() || '';
      const video = document.querySelector('video');
      const stream = video?.srcObject;
      return {
        statusText,
        hasVideo: !!video,
        hasStream: !!stream,
        readyState: video?.readyState ?? -1,
        videoWidth: video?.videoWidth ?? 0,
        videoHeight: video?.videoHeight ?? 0,
        paused: video?.paused ?? true,
      };
    });

    last = state;
    console.log('probe', i, JSON.stringify(state));

    if (
      state.statusText.toLowerCase().includes('connected') &&
      state.hasStream &&
      state.readyState >= 2 &&
      state.videoWidth > 0 &&
      state.videoHeight > 0
    ) {
      success = true;
      break;
    }
    await sleep(500);
  }

  await page.screenshot({ path: '/tmp/rc-webrtc-e2e.png', fullPage: true });

  // 采样视频区域中心像素，用于区分真实桌面与纯灰占位图
  const sample = await page.evaluate(() => {
    const video = document.querySelector('video');
    if (!video || !video.videoWidth || !video.videoHeight) return null;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const center = ctx.getImageData(Math.floor(canvas.width / 2), Math.floor(canvas.height / 2), 1, 1).data;
    const quarter = ctx.getImageData(Math.floor(canvas.width / 4), Math.floor(canvas.height / 4), 1, 1).data;
    return {
      center: Array.from(center),
      quarter: Array.from(quarter),
      w: canvas.width,
      h: canvas.height,
    };
  });

  if (success) {
    console.log('E2E_SUCCESS', JSON.stringify(last));
    console.log('VIDEO_SAMPLE', JSON.stringify(sample));
  } else {
    console.log('E2E_FAIL', JSON.stringify(last));
    console.log('VIDEO_SAMPLE', JSON.stringify(sample));
    process.exitCode = 1;
  }
} catch (err) {
  await page.screenshot({ path: '/tmp/rc-webrtc-e2e-fail.png', fullPage: true }).catch(() => {});
  console.error('E2E_ERROR', err?.stack || String(err));
  process.exitCode = 1;
} finally {
  await browser.close();
}
