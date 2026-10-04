// The publication rule for files the cloud finds on Drive by itself - the
// SAME rule as stages/13_app/share_set.py, proven equal by both test suites
// reading stages/13_app/nudity_cases.json. Krish, 2026-10-04: "it is
// imperative there is no sensitive nudity in this (naked babies or armpits or
// genuine family moment like giving birth is fine, but pictures of my ex
// girlfriends naked is not)".

export type Sens = { nudity?: string; subject_age?: string; sexual?: string };

// Why this must not be shared, or "" when it may be. `released` is Krish's
// own per-file share=yes and lifts ONLY an adult-nudity hold.
export function nudityHold(sensitivity: string, sens: Sens, released: boolean): string {
  const s = (sensitivity || "").trim().toLowerCase();
  const nudity = (sens.nudity || "").trim().toLowerCase();
  const age = (sens.subject_age || "").trim().toLowerCase();
  if (s === "") return "never classified for sensitivity";
  if (s === "intimate") return "sensitivity is intimate";
  if ((sens.sexual || "").trim().toLowerCase() === "yes") return "the nudity pass says sexual";
  if (nudity === "partial" || nudity === "full") {
    if (age === "child") return "";
    if (released) return "";
    return "nudity with an adult or unclear age - needs Krish's share=yes";
  }
  if (nudity !== "" && nudity !== "none") return "nudity verdict not understood: " + nudity;
  if (s === "private-family") return nudity === "none" ? "" : "private-family with no nudity verdict";
  if (s !== "none") return "sensitivity is " + s;
  return "";
}

export type Verdict = {
  kind?: string; sensitivity?: string;
  nudity?: string; subject_age?: string; sexual?: string;
};

// A cloud file is shown only if it is a photograph (or video) AND passes the
// nudity rule. The cloud never has a human release, so released is false.
export function cloudHold(media: "photo" | "video", v: Verdict): string {
  if (media === "photo" && (v.kind || "") !== "photo") return "not a photograph (" + (v.kind || "no kind") + ")";
  return nudityHold(v.sensitivity || "", v, false);
}
