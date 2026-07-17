import type { Metadata } from "next";
import { SITE_DATA } from "@/lib/site-data.generated";
import "./globals.css";

export const metadata: Metadata = {
  title: SITE_DATA.meta.title,
  description: SITE_DATA.meta.description,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
