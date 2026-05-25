import { test, expect, type Page } from "@playwright/test"

const MODULE_ERROR = /importing a module script|module script failed|failed to (load|fetch).*module/i

function trackErrors(page: Page): string[] {
  const errors: string[] = []
  page.on("pageerror", (e) => errors.push(e.message))
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text())
  })
  return errors
}

test("app boots without module-loading errors (WebKit)", async ({ page }) => {
  const errors = trackErrors(page)
  await page.goto("/")
  await expect(page.locator("#root")).not.toBeEmpty()
  expect(errors.join("\n")).not.toMatch(MODULE_ERROR)
})

test("lazy route loads on direct navigation (WebKit)", async ({ page }) => {
  // /wiki is a code-split route — directly loading it exercises the dynamic
  // import() that previously failed in WKWebView (crossorigin / cold first load).
  const errors = trackErrors(page)
  await page.goto("/wiki")
  await expect(page.locator("#root")).not.toBeEmpty()
  expect(errors.join("\n")).not.toMatch(MODULE_ERROR)
})

test("client-side navigation between routes works (WebKit)", async ({ page }) => {
  const errors = trackErrors(page)
  await page.goto("/")
  await page.getByRole("link", { name: "Wiki" }).click()
  await expect(page).toHaveURL(/\/wiki$/)
  await page.getByRole("link", { name: "Ask" }).click()
  await expect(page).toHaveURL(/\/ask$/)
  expect(errors.join("\n")).not.toMatch(MODULE_ERROR)
})
