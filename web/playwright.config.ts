import { defineConfig, devices } from "@playwright/test";

// The three phone widths the floor is held to. Chromium from the image; no
// browser download.
const exe = process.env.CHROME_PATH || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";
const phone = (name: string, width: number, height: number) => ({
  name,
  use: { ...devices["Pixel 7"], viewport: { width, height }, launchOptions: { executablePath: exe } },
});

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: process.env.BASE_URL || "http://localhost:3000", trace: "off" },
  projects: [phone("360", 360, 740), phone("390", 390, 844), phone("430", 430, 932)],
});
