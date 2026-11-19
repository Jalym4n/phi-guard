import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FindingList } from "./FindingList";
import { HighlightedText } from "./HighlightedText";
import { PrivacyBadge } from "./PrivacyBadge";
import { RiskMeter, VerdictCard } from "./Verdict";
import { Toggle } from "./ui";

describe("HighlightedText", () => {
  it("labels every highlight in words, not just colour", () => {
    render(
      <HighlightedText
        text="Patient: Ann Lee, SIN 123 456 782"
        label="Original"
        highlights={[
          { id: "a", start: 9, end: 16, kind: "PATIENT_NAME", needsCheck: true },
          { id: "b", start: 22, end: 33, kind: "SIN", kept: true },
        ]}
      />,
    );
    const region = screen.getByRole("region", { name: "Original" });
    const marks = region.querySelectorAll("mark");
    expect(marks).toHaveLength(2);
    expect(marks[0]).toHaveTextContent("Name · check");
    expect(marks[0]).toHaveTextContent("Ann Lee");
    expect(marks[1]).toHaveTextContent("kept");
    expect(region).toHaveAttribute("tabindex", "0");
  });
});

describe("FindingList", () => {
  it("toggles Remove/Keep and focuses findings", async () => {
    const onToggle = vi.fn();
    const onFocus = vi.fn();
    const onDelete = vi.fn();
    render(
      <FindingList
        items={[
          { id: "1", start: 0, kind: "PHONE", label: "Phone number", text: "416-555-0142", needsCheck: false, remove: true, manual: false },
          { id: "m", start: 5, kind: "OTHER", label: "Other", text: "Lakeview", needsCheck: true, remove: true, manual: true },
        ]}
        onToggle={onToggle}
        onFocus={onFocus}
        onDeleteManual={onDelete}
      />,
    );
    const phone = screen.getByRole("group", { name: /Phone number/ });
    expect(within(phone).getByRole("button", { name: "Remove" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(within(phone).getByRole("button", { name: "Keep" }));
    expect(onToggle).toHaveBeenCalledWith("1", false);
    await userEvent.click(screen.getByRole("button", { name: /Show in text: Phone number/ }));
    expect(onFocus).toHaveBeenCalledWith("1");
    expect(screen.getByText("Please check")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Undo/ }));
    expect(onDelete).toHaveBeenCalledWith("m");
  });

  it("has an empty state", () => {
    render(<FindingList items={[]} onToggle={vi.fn()} onFocus={vi.fn()} onDeleteManual={vi.fn()} />);
    expect(screen.getByText("Nothing found yet.")).toBeInTheDocument();
  });
});

describe("Verdict and risk meter", () => {
  it("shows the verdict with an icon and words", () => {
    render(<VerdictCard verdict="block" title="Do not use this document" detail="..." />);
    expect(screen.getByRole("status")).toHaveTextContent("Red light");
    expect(screen.getByRole("status")).toHaveTextContent("Do not use this document");
  });
  it("exposes the score to assistive technology", () => {
    render(<RiskMeter score={42} verdict="review" />);
    const meter = screen.getByRole("meter", { name: "Risk score" });
    expect(meter).toHaveAttribute("aria-valuenow", "42");
  });
});

describe("Toggle", () => {
  it("is a labelled switch", async () => {
    const onChange = vi.fn();
    render(<Toggle id="t" label="Names" description="e.g. Patient: Jane" checked onChange={onChange} />);
    const sw = screen.getByRole("switch", { name: "Names" });
    expect(sw).toHaveAttribute("aria-checked", "true");
    await userEvent.click(sw);
    expect(onChange).toHaveBeenCalledWith(false);
  });
});

describe("PrivacyBadge", () => {
  it("opens an explanation", async () => {
    render(<PrivacyBadge />);
    await userEvent.click(screen.getByRole("button", { name: /Runs only on this computer/ }));
    expect(screen.getByText(/never connects to the internet/)).toBeInTheDocument();
  });
});
