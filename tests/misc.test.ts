import { describe, it, expect, afterAll, vi } from "vitest";
import { sha256, slugify, today } from "../src/utils/misc";
import fs from "fs-extra";
import path from "node:path";
import os from "node:os";

describe("misc utils", () => {
  describe("sha256", () => {
    const tempDir = path.join(os.tmpdir(), "wiki-test-" + Math.random().toString(36).slice(2));

    it("should return the correct sha256 hash of a file", async () => {
      await fs.ensureDir(tempDir);
      const testFile = path.join(tempDir, "test.txt");
      await fs.writeFile(testFile, "hello world");

      const hash = await sha256(testFile);
      // echo -n "hello world" | shasum -a 256 -> b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9
      expect(hash).toBe("sha256:b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9");
    });

    it("should reject with a missing-file error if the file does not exist", async () => {
      const nonExistentFile = path.join(tempDir, "nope.txt");
      await expect(sha256(nonExistentFile)).rejects.toMatchObject({ code: "ENOENT" });
    });

    afterAll(async () => {
      await fs.remove(tempDir);
    });
  });

  describe("slugify", () => {
    it("should convert strings to lowercase and replace spaces with hyphens", () => {
      expect(slugify("Hello World")).toBe("hello-world");
    });

    it("should handle special characters and accents", () => {
      expect(slugify("Héllö Wörld!")).toBe("hello-world");
    });

    it("should handle multiple hyphens and trim them", () => {
      expect(slugify("---Hello---World---")).toBe("hello-world");
    });

    it("should truncate to 80 characters", () => {
      const longString = "a".repeat(100);
      expect(slugify(longString)).toHaveLength(80);
    });
  });

  describe("today", () => {
    it("should return today's date in YYYY-MM-DD format", () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date("2026-05-12T12:00:00Z"));
      try {
        const date = today();
        expect(date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
        // today() uses toISOString().slice(0, 10) which is UTC
        expect(date).toBe("2026-05-12");
      } finally {
        vi.useRealTimers();
      }
    });
  });
});
