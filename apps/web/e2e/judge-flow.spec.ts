import { expect, test } from '@playwright/test'

test.beforeEach(async ({ request }) => {
  const response = await request.post('/api/v1/demo/reset')
  expect(response.ok()).toBeTruthy()
})

test('live recovery demo shows failure, recommendation, and recovered outcome', async ({ page }) => {
  await page.goto('/')
  await page.getByTestId('start-guided-journey').click()
  await expect(page.getByText('STANDARD PAYMENT LINK').first()).toBeVisible()
  await expect(page.getByText('All pass')).toBeVisible()
  await page.getByTestId('complete-guided-recovery').click()
  await expect(page.getByText('Revenue recovered')).toBeVisible()
  await expect(page.getByText('RECOVERED').first()).toBeVisible()
})

test('hero recovery reaches recovered exactly once', async ({ page, request }) => {
  await page.goto('/inbox')
  await page.getByRole('link', { name: /pay_test_hero_001/ }).click()
  await expect(page.getByText('STANDARD PAYMENT LINK').first()).toBeVisible()
  await page.getByTestId('execute-action').click()
  await expect(page.getByText(/SIMULATED OFFLINE ACTION/)).toBeVisible()
  const paid = await request.post('/api/v1/demo/webhooks/hero-payment-link-paid')
  expect(paid.ok()).toBeTruthy()
  const duplicate = await request.post('/api/v1/demo/webhooks/hero-payment-link-paid')
  expect((await duplicate.json()).created).toBeFalsy()
  await page.reload()
  await expect(page.getByText('RECOVERED').first()).toBeVisible()
})

test('judge cases expose no-action, opt-out block, and uncertain review', async ({ page }) => {
  await page.goto('/inbox')
  await page.getByRole('link', { name: /pay_test_low_value_001/ }).click()
  await expect(page.getByText('NO ACTION').first()).toBeVisible()
  await page.goto('/inbox')
  await page.getByRole('link', { name: /pay_test_opt_out_001/ }).click()
  await expect(page.getByText('OPT OUT').first()).toBeVisible()
  await page.goto('/inbox')
  await page.getByRole('link', { name: /pay_test_uncertain_001/ }).click()
  await expect(page.getByText('HUMAN REVIEW').first()).toBeVisible()
})

test('decision surgery flips a cloned decision and evaluation shows frozen metadata', async ({ page }) => {
  await page.goto('/inbox')
  await page.getByRole('link', { name: /pay_test_hero_001/ }).click()
  await page.getByRole('link', { name: 'Open Decision Surgery' }).click()
  await page.getByLabel('Failed amount, subunits').fill('5000')
  await page.getByTestId('run-surgery').click()
  await expect(page.getByText('SIMULATION ONLY')).toBeVisible()
  await expect(page.getByText('false', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: '60-case Proof' }).click()
  await expect(page.getByText('What AI changed')).toBeVisible()
  await expect(page.getByText(/final-evaluation.json/)).toBeVisible()
  await page.getByTestId('run-batch').click()
  await expect(page.getByText('60/60', { exact: true })).toBeVisible({ timeout: 10_000 })
})

test('merchant impact exposes refusal and production proof', async ({ page }) => {
  await page.goto('/inbox')
  await expect(page.getByText('is at risk.')).toBeVisible()
  await page.getByRole('link', { name: 'See a case where Recourse refuses to act' }).click()
  await expect(page.getByText('HUMAN REVIEW').first()).toBeVisible()
  await page.getByRole('link', { name: 'Production' }).click()
  await expect(page.getByText('Ten controls in one path')).toBeVisible()
  await expect(page.getByText('10,000 signed events')).toBeVisible()
})

test('all five judge routes render at the demo viewport', async ({ page }) => {
  await page.goto('/')
  await page.screenshot({ path: 'test-results/screenshots/live-demo-1366x768.png', fullPage: true })
  await page.goto('/inbox')
  await page.screenshot({ path: 'test-results/screenshots/inbox-1366x768.png', fullPage: true })
  await page.getByRole('link', { name: /pay_test_hero_001/ }).click()
  await page.screenshot({ path: 'test-results/screenshots/workbench-1366x768.png', fullPage: true })
  await page.getByRole('link', { name: 'Open Decision Surgery' }).click()
  await page.screenshot({ path: 'test-results/screenshots/surgery-1366x768.png', fullPage: true })
  await page.goto('/evaluation')
  await page.screenshot({ path: 'test-results/screenshots/evaluation-1366x768.png', fullPage: true })
})

test('judge routes contain their layout at 1280 by 720', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 })
  for (const route of ['/', '/inbox', '/evaluation', '/production']) {
    await page.goto(route)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    expect(overflow).toBeLessThanOrEqual(0)
  }
})
