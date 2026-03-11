"use client";
import { useEffect } from "react";

export default function AuthCookieSync() {
  useEffect(() => {
  // No-op: with HttpOnly sessions, SSR sees auth via cookies without JS bridges.
  }, []);
  return null;
}
