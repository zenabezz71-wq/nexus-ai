"use client";
import { useEffect } from "react";

export default function AppHome() {
  useEffect(() => {
    window.location.replace("/app/contacts");
  }, []);
  return <p className="muted" style={{ padding: 30 }}>Opening your workspace...</p>;
}
