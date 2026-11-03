import { expect, test } from '@playwright/test';

const verifiedResponse = {
  answer: 'No completed sales are recorded for today.',
  intent: 'sales_today',
  sources: ['completed orders'],
  generated_at: '2026-11-01T00:00:00Z',
  grounded: true,
};

test('a refreshed voice page starts idle without a microphone error', async ({ page }) => {
  await page.goto('/voice-assistant');
  await expect(page.locator('.assistant-error[role="alert"]')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Ask your business a question.' })).toBeVisible();
  await page.reload();
  await expect(page.locator('.assistant-error[role="alert"]')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Ask your business a question.' })).toBeVisible();
});

async function installVoiceFakes(page: import('@playwright/test').Page, includeSpeaker = true) {
  await page.addInitScript((speakerEnabled) => {
    type Recognition = { onresult?: (event: unknown) => void; onend?: () => void; onerror?: (event: unknown) => void; start: () => void; stop: () => void; abort: () => void; lang: string; continuous: boolean; interimResults: boolean };
    const recognitions: Recognition[] = [];
    class FakeRecognition implements Recognition {
      lang = 'en-US'; continuous = false; interimResults = false;
      onresult?: (event: unknown) => void; onend?: () => void; onerror?: (event: unknown) => void;
      start = () => undefined;
      stop = () => this.onend?.();
      abort = () => this.onend?.();
      constructor() { recognitions.push(this); }
    }
    window.sessionStorage.setItem('morrow.access-token', 'voice-e2e-token');
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: FakeRecognition });
    Object.defineProperty(window, 'webkitSpeechRecognition', { configurable: true, value: FakeRecognition });
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
      getUserMedia: async () => ({ getTracks: () => [{ stop: () => undefined }] }),
    } });
    Object.assign(window, { __voiceTestRecognitions: recognitions, __voiceTestSpoken: [] as string[] });
    if (speakerEnabled) {
      class FakeUtterance { constructor(public text: string) {} onend: (() => void) | null = null; onerror: (() => void) | null = null; rate = 1; pitch = 1; }
      Object.defineProperty(window, 'SpeechSynthesisUtterance', { configurable: true, value: FakeUtterance });
      Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: {
        speak: (utterance: FakeUtterance) => { (window as unknown as Window & { __voiceTestSpoken: string[] }).__voiceTestSpoken.push(utterance.text); utterance.onend?.(); },
        cancel: () => undefined, getVoices: () => [], addEventListener: () => undefined, removeEventListener: () => undefined,
      } });
    } else {
      Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: undefined });
      Object.defineProperty(window, 'SpeechSynthesisUtterance', { configurable: true, value: undefined });
    }
  }, includeSpeaker);
}

test('a final browser transcript is submitted once, displayed, and spoken', async ({ page }) => {
  await installVoiceFakes(page);
  let submissions = 0;
  await page.route('**/api/v1/voice/ask', async route => {
    submissions += 1;
    expect(JSON.parse(route.request().postData() ?? '{}')).toMatchObject({ question: "Show today's sales", consent_to_store_transcript: false });
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(verifiedResponse) });
  });
  await page.goto('/voice-assistant');
  await page.getByRole('button', { name: 'Start voice input' }).click();
  await expect.poll(() => page.evaluate(() => (window as unknown as Window & { __voiceTestRecognitions: unknown[] }).__voiceTestRecognitions.length)).toBe(1);
  await page.evaluate(() => {
    const recognition = (window as unknown as Window & { __voiceTestRecognitions: { onresult?: (event: unknown) => void }[] }).__voiceTestRecognitions[0];
    recognition.onresult?.({ resultIndex: 0, results: [{ 0: { transcript: "Show today's sales" }, isFinal: true, length: 1 }, { length: 1 }] });
    // Some Web Speech engines send this after the final result while their
    // microphone session is shutting down. It must not hide a valid answer.
    (recognition as { onerror?: (event: unknown) => void }).onerror?.({ error: 'audio-capture' });
  });
  await expect(page.getByText(verifiedResponse.answer)).toBeVisible();
  await expect.poll(() => page.evaluate(() => (window as unknown as Window & { __voiceTestSpoken: string[] }).__voiceTestSpoken)).toEqual([verifiedResponse.answer]);
  expect(submissions).toBe(1);
});

test('a received response stays visible when speech synthesis is unsupported', async ({ page }) => {
  await installVoiceFakes(page, false);
  await page.route('**/api/v1/voice/ask', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(verifiedResponse) }));
  await page.goto('/voice-assistant');
  await page.getByLabel('Recognized speech or typed command').fill("Show today's sales");
  await page.getByRole('button', { name: 'Ask' }).click();
  await expect(page.getByText(verifiedResponse.answer)).toBeVisible();
  await expect(page.getByText(/Speaker playback is not supported/i)).toBeVisible();
});

test('a backend failure is announced instead of leaving the assistant processing', async ({ page }) => {
  await installVoiceFakes(page);
  await page.route('**/api/v1/voice/ask', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { message: 'Voice service is temporarily unavailable.' } }) }));
  await page.goto('/voice-assistant');
  await page.getByLabel('Recognized speech or typed command').fill("Show today's sales");
  await page.getByRole('button', { name: 'Ask' }).click();
  await expect(page.locator('.assistant-error[role="alert"]')).toContainText('Voice service is temporarily unavailable.');
  await expect(page.getByRole('heading', { name: 'Voice assistant needs your attention.' })).toBeVisible();
});

test('a browser speech-service network error is recoverable and does not hide text input', async ({ page }) => {
  await installVoiceFakes(page);
  await page.goto('/voice-assistant');
  await page.getByRole('button', { name: 'Start voice input' }).click();
  await page.evaluate(() => {
    const recognition = (window as unknown as Window & { __voiceTestRecognitions: { onerror?: (event: unknown) => void }[] }).__voiceTestRecognitions[0];
    recognition.onerror?.({ error: 'network' });
  });
  await expect(page.locator('.assistant-error[role="alert"]')).toContainText('speech service');
  await expect(page.getByRole('button', { name: 'Retry voice input' })).toBeVisible();
  await expect(page.getByLabel('Recognized speech or typed command')).toBeEnabled();
});
