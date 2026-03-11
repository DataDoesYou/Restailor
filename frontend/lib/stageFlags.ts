export type StageLabel = "applied" | "interviewing" | "offer" | "hired";

export type StageFlagInput = {
  interviewing?: boolean | null;
  offer?: boolean | null;
  hired?: boolean | null;
};

export type StageFlagState = {
  interviewing: boolean;
  offer: boolean;
  hired: boolean;
};

export function normalizeStageFlags(flags?: StageFlagInput | null): StageFlagState {
  const interviewing = !!flags?.interviewing;
  let offer = !!flags?.offer;
  let hired = !!flags?.hired;

  if (!interviewing) {
    offer = false;
    hired = false;
  }

  if (!offer) {
    hired = false;
  }

  if (hired) {
    return { interviewing: true, offer: true, hired: true };
  }

  if (offer) {
    return { interviewing: true, offer: true, hired: false };
  }

  if (interviewing) {
    return { interviewing: true, offer: false, hired: false };
  }

  return { interviewing: false, offer: false, hired: false };
}

export function applyStageToggle(prev: StageFlagState, key: keyof StageFlagState, next: boolean): StageFlagState {
  let interviewing = prev.interviewing;
  let offer = prev.offer;
  let hired = prev.hired;

  if (key === "interviewing") {
    interviewing = next;
    if (!interviewing) {
      offer = false;
      hired = false;
    }
  } else if (key === "offer") {
    offer = next;
    if (offer) {
      interviewing = true;
    } else {
      hired = false;
    }
  } else if (key === "hired") {
    hired = next;
    if (hired) {
      offer = true;
      interviewing = true;
    }
  }

  return normalizeStageFlags({ interviewing, offer, hired });
}

export function deriveStageLabel(isApplied: boolean, flags: StageFlagState): StageLabel | null {
  if (flags.hired) return "hired";
  if (flags.offer) return "offer";
  if (flags.interviewing) return "interviewing";
  return isApplied ? "applied" : null;
}
