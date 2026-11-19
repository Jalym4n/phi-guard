import { describeCounts, kindStyle } from "./kinds";
import { findAll, offsetIn, trimSpan } from "./selection";
import { api, ApiError, initToken, setTokenForTests } from "./api";

describe("describeCounts", () => {
  it("writes a plain-language summary with plurals", () => {
    expect(describeCounts({ PATIENT_NAME: 2, OHIP_NUMBER: 1 })).toBe(
      "Found 3 patient details: 2 names, 1 health card number.",
    );
    expect(describeCounts({})).toBe("No patient details found.");
  });
  it("gives every kind a label, with a fallback", () => {
    expect(kindStyle("SIN").label).toBe("Social insurance number");
    expect(kindStyle("WHATEVER").label).toBe("Detail");
  });
});

describe("selection helpers", () => {
  it("ignores labels marked data-skip when computing offsets", () => {
    const div = document.createElement("div");
    div.innerHTML = 'Hi <mark><span data-skip>Name</span><span>Ann Lee</span></mark>, ok';
    const text = div.querySelectorAll("span")[1]!.firstChild!;
    expect(offsetIn(div, text, 0)).toBe(3);
    expect(offsetIn(div, text, 3)).toBe(6);
    const after = div.lastChild!;
    expect(offsetIn(div, after, 2)).toBe(12);
    expect(offsetIn(div, div, div.childNodes.length)).toBe(14);
    expect(offsetIn(div, div, 1)).toBe(3);
  });
  it("trims spans and finds all occurrences", () => {
    expect(trimSpan("  ab  ", 0, 6)).toEqual({ start: 2, end: 4 });
    expect(findAll("x Lee y Lee", "Lee")).toEqual([
      { start: 2, end: 5 },
      { start: 8, end: 11 },
    ]);
    expect(findAll("abc", "")).toEqual([]);
  });
});

describe("api client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    setTokenForTests(null);
  });

  it("reads the token from the fragment, removes it from the URL, and sends it as a header", async () => {
    window.history.replaceState(null, "", "/#token=abc123");
    expect(initToken()).toBe("abc123");
    expect(window.location.hash).toBe("");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.health();
    const headers = fetchMock.mock.calls[0]![1].headers as Headers;
    expect(headers.get("X-PHI-Guard-Token")).toBe("abc123");
    expect(initToken()).toBe("abc123"); // survives a refresh via sessionStorage
  });

  it("turns server errors into plain-language messages", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "Too big." }), { status: 413 })));
    await expect(api.scan("x")).rejects.toEqual(new ApiError("Too big.", 413));
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(api.scan("x")).rejects.toThrow("Studio isn't responding");
  });

  it("never stores patient text in browser storage", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ findings: [], summary: [] }))));
    await api.scan("Patient: Eleanor Whitfield");
    const dump = JSON.stringify({ ...window.localStorage }) + JSON.stringify({ ...window.sessionStorage });
    expect(dump).not.toContain("Whitfield");
  });
});
