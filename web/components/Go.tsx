"use client";
import Link, { useLinkStatus } from "next/link";
import type { ComponentProps } from "react";

// A choice on the Find screen that answers the moment it is touched (Krish,
// 2026-10-12: "glitchy ... so slow and laggy"). Before: a tap changed nothing
// on screen for over a second while the next screen was made, so a second tap
// landed on the old one. Now each choice on screen is fetched before it is
// tapped (prefetch: the next screen is usually already here), and a tap that
// still has to wait marks its own button at once.
function Pressed() {
  const { pending } = useLinkStatus();
  return <span className={pending ? "pressed on" : "pressed"} aria-hidden="true" />;
}

export default function Go({ children, ...props }: ComponentProps<typeof Link>) {
  return (
    <Link prefetch {...props}>
      {children}
      <Pressed />
    </Link>
  );
}
