import type { Metadata } from "next";import "./globals.css";
export const metadata:Metadata={title:"NEXUS AI",description:"AI business workspace"};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
