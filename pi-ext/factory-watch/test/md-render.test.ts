import { describe, expect, test } from "vitest";
import { renderMarkdown, stripDocFrontmatter } from "../src/md-render.js";

describe("stripDocFrontmatter", () => {
  test("removes a leading frontmatter block", () => {
    expect(stripDocFrontmatter("---\nid: T-1\n---\n\n# Title\n")).toBe("\n# Title\n");
  });

  test("leaves a document with no frontmatter untouched", () => {
    // Plans historically have none, but trace exempt/defer can add one later.
    expect(stripDocFrontmatter("# Title\n\nbody\n")).toBe("# Title\n\nbody\n");
  });

  test("does not treat a mid-document hrule as frontmatter", () => {
    const src = "# Title\n\n---\n\nmore\n";
    expect(stripDocFrontmatter(src)).toBe(src);
  });
});

describe("renderMarkdown", () => {
  test("renders headings and collects a toc with stable slugs", () => {
    const out = renderMarkdown("# One\n\n## Two Words\n");
    expect(out.html).toContain('<h1 id="one">One</h1>');
    expect(out.html).toContain('<h2 id="two-words">Two Words</h2>');
    expect(out.toc).toEqual([
      { level: 1, text: "One", slug: "one" },
      { level: 2, text: "Two Words", slug: "two-words" },
    ]);
  });

  test("disambiguates duplicate heading slugs", () => {
    const out = renderMarkdown("## Steps\n\n## Steps\n");
    expect(out.toc.map((t) => t.slug)).toEqual(["steps", "steps-2"]);
  });

  test("renders fenced code literally without highlighting", () => {
    const out = renderMarkdown("```python\nx = 1 < 2\n```\n");
    expect(out.html).toContain('<pre><code class="language-python">x = 1 &lt; 2\n</code></pre>');
  });

  test("markdown inside a fence is not interpreted", () => {
    const out = renderMarkdown("```\n# not a heading\n**not bold**\n```\n");
    expect(out.html).not.toContain("<h1");
    expect(out.html).not.toContain("<strong>");
  });

  test("escapes html in prose", () => {
    const out = renderMarkdown("a <script>alert(1)</script> b\n");
    expect(out.html).not.toContain("<script>");
    expect(out.html).toContain("&lt;script&gt;");
  });

  test("renders bullets, inline code, bold, italic and links", () => {
    const out = renderMarkdown("- a `code` b **bold** c *it* d [x](http://e)\n");
    expect(out.html).toContain("<ul>");
    expect(out.html).toContain("<code>code</code>");
    expect(out.html).toContain("<strong>bold</strong>");
    expect(out.html).toContain("<em>it</em>");
    expect(out.html).toContain('<a href="http://e">x</a>');
  });

  test("renders ordered lists", () => {
    expect(renderMarkdown("1. first\n2. second\n").html).toContain("<ol>");
  });

  test("renders checkboxes and derives progress", () => {
    const out = renderMarkdown("- [x] done\n- [ ] todo\n- [ ] other\n");
    expect(out.html).toContain('<input type="checkbox" checked disabled>');
    expect(out.progress).toEqual({ done: 1, total: 3 });
  });

  test("progress is null when a document has no checkboxes", () => {
    expect(renderMarkdown("# Spec\n\nprose\n").progress).toBeNull();
  });

  test("renders tables", () => {
    const out = renderMarkdown("| a | b |\n|---|---|\n| 1 | 2 |\n");
    expect(out.html).toContain("<table>");
    expect(out.html).toContain("<th>a</th>");
    expect(out.html).toContain("<td>2</td>");
  });

  test("renders blockquotes and hrules", () => {
    const out = renderMarkdown("> quoted\n\n---\n");
    expect(out.html).toContain("<blockquote>");
    expect(out.html).toContain("<hr>");
  });

  test("renders paragraphs", () => {
    expect(renderMarkdown("hello world\n").html).toContain("<p>hello world</p>");
  });

  test("handles an empty document", () => {
    expect(renderMarkdown("")).toEqual({ html: "", toc: [], progress: null });
  });

  test("a pipe line with no table separator terminates instead of hanging", () => {
    // Regression: this line matches the paragraph loop's break condition but no
    // block matcher, so it used to leave index unadvanced and spin forever.
    const out = renderMarkdown("| not really a table\n\nafter\n");
    expect(out.html).toContain("after");
  });

  test("every line shape that can break the paragraph loop still terminates", () => {
    for (const line of ["|", "|||", "  |  ", ">", "#", "``"]) {
      const out = renderMarkdown(`${line}\n\ntail\n`);
      expect(out.html).toContain("tail");
    }
  });

  test("an unterminated fence does not lose the rest of the document", () => {
    const out = renderMarkdown("```\nx = 1\n");
    expect(out.html).toContain("x = 1");
  });
});
