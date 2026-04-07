const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.on('console', msg => console.log('BROWSER CONSOLE:', msg.text()));

  await page.goto('http://localhost:8000/accounts/login/');
  await page.fill('input[name="username"]', 'admin');
  await page.fill('input[name="password"]', 'admin');
  await page.click('button[type="submit"]');
  await page.waitForTimeout(5000);

  await page.goto('http://localhost:8000/services/calendar/');
  await page.waitForTimeout(5000);

  const timeSlot = await page.$('.fc-daygrid-day-frame');
  if (timeSlot) {
      const box = await timeSlot.boundingBox();
      await page.mouse.move(box.x + box.width/2, box.y + 10);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width/2, box.y + 70);
      await page.mouse.up();
  } else {
      console.log('No timegrid slots found');
  }

  await page.waitForTimeout(3000);
  
  const frameElement = await page.$('#scheduling-iframe');
  if (frameElement) {
      const frame = await frameElement.contentFrame();
      if(frame) {
          try {
             await frame.waitForSelector('input[name="scheduled_end_at"]', { timeout: 5000 });
          }catch(e){
              console.log('Timeout waiting for input');
          }
          const endVal = await frame.evaluate(() => {
              const el = document.querySelector('input[name="scheduled_end_at"]');
              return el ? el.value : 'NO_ELEMENT';
          });
          console.log('INPUT VALUE:', endVal);
      } else {
          console.log('NO FRAME CONTENT');
      }
  }
  
  await browser.close();
})();
