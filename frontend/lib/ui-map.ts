export type UiEntry = {
  id: string;
  label: string;
  ariaLabel: string;
  testId: string;
  selector: string;
  section: string;
};

export function formatUiMap(entries: UiEntry[]) {
  // Keep fields in consistent order
  return JSON.stringify(
    entries.map((e) => ({
      id: e.id,
      label: e.label,
      ariaLabel: e.ariaLabel,
      testId: e.testId,
      selector: e.selector,
      section: e.section,
    })),
    null,
    2
  );
}
