import { expect, test } from '@playwright/test';

test('all primary navigation destinations render without the not-found state', async ({ page }) => {
  test.setTimeout(60_000);
  await page.goto('/');
  const destinations = await page.locator('nav.side-nav a').evaluateAll(links =>
    links.map(link => (link as HTMLAnchorElement).getAttribute('href')).filter(Boolean),
  );
  expect(destinations).toHaveLength(26);
  for (const path of destinations) {
    await page.goto(path!);
    await expect(page.locator('.not-found-panel')).toHaveCount(0);
    await expect(page.locator('main h1').first()).toBeVisible();
  }
});

test('command palette supports keyboard search and navigation', async ({ page }) => {
  await page.goto('/');
  await page.keyboard.press('Control+k');
  const search = page.getByPlaceholder('Where would you like to go?');
  await expect(search).toBeFocused();
  await search.fill('Suppliers');
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/suppliers$/);
  await expect(page.getByRole('heading', { name: 'Suppliers' })).toBeVisible();
});

test('desktop sidebar collapses with accessible route names and remembers theme', async ({ page }) => {
  test.skip(/mobile/.test(test.info().project.name), 'Desktop-only sidebar collapse control.');
  await page.goto('/');
  await page.getByRole('button', { name: 'Collapse sidebar' }).click();
  await expect(page.locator('.sidebar')).toHaveClass(/sidebar-collapsed/);
  await expect(page.locator('nav.side-nav').getByRole('link', { name: 'Inventory' })).toBeVisible();
  await page.reload();
  await expect(page.locator('.sidebar')).toHaveClass(/sidebar-collapsed/);
  await page.getByRole('button', { name: 'Switch to dark mode' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
});

test('mobile navigation opens, navigates, and closes', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'Runs in the mobile browser project.');
  await page.goto('/');
  await page.getByRole('button', { name: 'Open navigation' }).click();
  const navigation = page.getByRole('navigation', { name: 'Main navigation' });
  await expect(navigation).toBeVisible();
  await navigation.getByRole('link', { name: 'Inventory' }).click();
  await expect(page).toHaveURL(/\/inventory$/);
  await expect(page.locator('.sidebar')).not.toHaveClass(/sidebar-open/);
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible();
});

test('POS receipt is explicitly a preview and does not claim to charge payment', async ({ page }) => {
  await page.goto('/pos', { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: /House blend coffee/ }).click();
  await expect(page.getByRole('button', { name: 'Remove one House blend coffee' })).toBeVisible();
  const previewReceipt = page.getByRole('button', { name: /Preview receipt/ });
  await expect(previewReceipt).toBeEnabled();
  await previewReceipt.click();
  await expect(page.getByRole('heading', { name: 'Receipt preview' })).toBeVisible();
  await expect(page.getByText('Preview only. Connect the payment API to complete a real charge.')).toBeVisible();
});

test('workspace previews provide page-specific sections, filterable settings, and record details', async ({ page }) => {
  await page.goto('/forecasting');
  await expect(page.getByRole('heading', { name: 'Historical demand and outlook' })).toBeVisible();
  await expect(page.getByText('The dashed blue series is illustrative')).toBeVisible();

  await page.goto('/settings');
  await page.getByRole('tab', { name: 'Integrations' }).click();
  await expect(page.getByRole('heading', { name: 'Integrations' })).toBeVisible();
  await expect(page.getByText('Payment provider')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save unavailable' })).toBeDisabled();

  await page.goto('/customers');
  const record = page.getByRole('button', { name: 'View Customers record Maya Chen' });
  await record.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toContainText('Illustrative detail only');
});

test('dashboard reporting period updates the illustrative KPIs and chart', async ({ page }) => {
  await page.goto('/');
  await page.locator('#dashboard-intro .story-step-next').click();
  await page.locator('#cinematic-feature .story-step-next').click();
  await page.locator('#menu .story-step-next').click();
  const revenue = page.locator('.command-metric .metric-value').first();
  await expect(revenue).toHaveText('$42,680');
  await page.getByLabel('Dashboard reporting period').selectOption('7 days');
  await expect(revenue).toHaveText('$10,842');
  await expect(page.locator('.command-chart-panel .chart-kpi strong')).toHaveText('$10,842');
  await expect(page.locator('.command-chart-panel .panel-heading p')).toContainText('7 days');
  await page.getByLabel('Dashboard reporting period').selectOption('90 days');
  await expect(revenue).toHaveText('$126,940');
});

test('dashboard videos are local, confined to the dashboard, and respect reduced motion', async ({ page }) => {
  await page.goto('/');
  const heroVideo = page.locator('.dashboard-hero video');
  await expect(heroVideo).toHaveAttribute('muted', '');
  await expect(heroVideo.locator('source')).toHaveAttribute('src', '/media/command-center-motion.mp4');
  await expect.poll(() => heroVideo.evaluate(video => (video as HTMLVideoElement).readyState)).toBeGreaterThanOrEqual(2);
  const cinematicVideo = page.locator('.cinematic-window video');
  await expect(cinematicVideo.locator('source')).toHaveAttribute('src', '/media/menu-slide-motion.mp4');
  await expect(cinematicVideo).toHaveAttribute('poster', '/media/menu-slide-poster.jpg');
  // The dashboard has its two contextual videos plus the intentionally global,
  // low-visibility ambient video layer.
  await expect(page.locator('video')).toHaveCount(3);
  await page.goto('/sales');
  // The ambient video stays behind the application shell; the two dashboard
  // videos are correctly confined to the dashboard story.
  await expect(page.locator('video')).toHaveCount(1);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.locator('.dashboard-hero')).toBeVisible();
  await expect(page.locator('.dashboard-hero-video')).toBeHidden();
  await page.locator('#dashboard-intro .story-step-next').click();
  await expect(cinematicVideo).toBeHidden();
  await expect.poll(() => page.locator('.cinematic-window').evaluate(node => getComputedStyle(node).backgroundImage)).toContain('menu-slide-poster.jpg');
});

test('cinematic chapter and dashboard panels reveal as slides enter', async ({ page }) => {
  await page.goto('/');
  const cinematic = page.locator('.cinematic-feature');
  await page.locator('#dashboard-intro .story-step-next').click();
  await expect(cinematic).toHaveClass(/is-visible/);
  const recommendations = page.locator('#recommendations');
  await page.locator('#cinematic-feature .story-step-next').click();
  await page.locator('#menu .story-step-next').click();
  await page.locator('#overview .story-step-next').click();
  await page.locator('#performance .story-step-next').click();
  await page.locator('#revenue .story-step-next').click();
  await page.locator('#operations .story-step-next').click();
  await expect(recommendations).toHaveClass(/is-visible/);
});

test('dashboard chapters replace each other on scroll and controls', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.dashboard-story-slide')).toHaveCount(8);
  const chapters = ['dashboard-intro', 'cinematic-feature', 'menu', 'overview', 'performance', 'revenue', 'operations', 'actions'];
  await expect(page.locator('#dashboard-intro')).toHaveClass(/is-current/);
  await page.mouse.wheel(0, 160);
  await expect(page.locator('#cinematic-feature')).toHaveClass(/is-current/);
  await expect(page.locator('#dashboard-intro')).toBeHidden();
  for (let index = 1; index < chapters.length - 1; index++) {
    await page.locator(`#${chapters[index]} .story-step-next`).click();
    await expect(page.locator(`#${chapters[index + 1]}`)).toHaveClass(/is-current/);
    await expect(page.locator(`#${chapters[index]}`)).toBeHidden();
  }
});

test('menu slide builds and clears a transparent bill preview', async ({ page }) => {
  await page.goto('/');
  await page.locator('#dashboard-intro .story-step-next').click();
  await page.locator('#cinematic-feature .story-step-next').click();
  const menu = page.locator('#menu');
  await expect(menu).toHaveClass(/is-current/);
  await expect(menu.locator('.menu-billing-backdrop')).toBeVisible();
  if ((await page.evaluate(() => innerWidth)) > 560) {
    const carousel = menu.locator('.menu-item-carousel');
    const cardHeight = await menu.locator('.menu-item-window').first().evaluate(node => node.clientHeight);
    const carouselHeight = await carousel.evaluate(node => node.clientHeight);
    expect(cardHeight).toBeLessThan(carouselHeight);
    expect(cardHeight).toBeLessThanOrEqual(260);
    await page.getByRole('button', { name: 'Next dishes' }).click();
    await expect.poll(() => carousel.evaluate(node => node.scrollLeft)).toBeGreaterThan(0);
  }
  await page.getByRole('button', { name: 'Add House blend coffee to bill' }).click();
  await page.getByRole('button', { name: 'Add one House blend coffee' }).click();
  await expect(menu.locator('.menu-bill-heading')).toContainText('2 items');
  await expect(menu.locator('.menu-bill-total strong').last()).toHaveText('$9.72');
  await page.getByRole('button', { name: 'Clear bill' }).click();
  await expect(menu.locator('.menu-bill-empty')).toBeVisible();
});

test('desktop, tablet, and narrow mobile dashboard layouts avoid horizontal overflow', async ({ page }) => {
  await page.goto('/');
  for (const width of [1920, 1440, 1280, 1024, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.locator('.dashboard-hero')).toBeVisible();
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    const dimensions = await page.evaluate(() => ({ viewport: innerWidth, content: document.documentElement.scrollWidth }));
    expect(dimensions.content, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(dimensions.viewport);
  }
});

test('account recovery explains the unavailable email integration', async ({ page }) => {
  await page.goto('/auth/reset-password');
  await expect(page.getByRole('heading', { name: 'Password reset unavailable' })).toBeVisible();
  await expect(page.getByText(/email delivery provider has not been configured/i)).toBeVisible();
  await expect(page.getByRole('button', { name: /send reset/i })).toHaveCount(0);
});

test('preview mode does not create an account or authentication session', async ({ page }) => {
  await page.goto('/auth/login');
  await page.getByLabel('Email address').fill('preview@example.test');
  await page.locator('input[autocomplete="current-password"]').fill('not-a-real-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.locator('.auth-form [role="alert"]')).toContainText('Authentication is not connected in preview mode');
  await expect(page.getByRole('heading', { name: 'Good to see you.' })).toBeVisible();
});
