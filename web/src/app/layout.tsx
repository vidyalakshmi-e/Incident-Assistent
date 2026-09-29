import type { Metadata, Viewport } from "next";
import { Archivo, Geist_Mono } from "next/font/google";

import { AppShell } from "@/components/shell/AppShell";
import { themeScript } from "@/components/shell/ThemeToggle";

import "./globals.css";

const archivo = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  axes: ["wdth"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Incident Intelligence", template: "%s · Incident Intelligence" },
  description:
    "Incident intelligence and guided troubleshooting: pattern families, novel-incident detection and evidence-backed resolutions.",
};

// Desktop only: a phone shows the 1280px desktop layout zoomed out rather than a separate phone layout.
export const viewport: Viewport = { width: 1280 };

// Direction contract (impeccable). Mirrored as an HTML comment in the emitted markup below.
const CONTRACT = `
THESIS: Read every incident like a forecast from historical analogs: what matched, at what odds, what was observed versus inferred. Refuses the dark KPI-tile observability console and the chat-bot assistant.
OWN-WORLD: Cool chart-paper ground, blue-black ink, cobalt for action/selection/known, red for novel/alert, amber for synthetic and caution, violet inferred, teal derived. Archivo across widths (condensed caps for chart annotation), Geist Mono for record IDs. Graticules only under real data; flat state fields; station-plot fingerprint; front-line causal chains.
STORY: The evaluator enters or picks a report, reads a verdict field, the grade of that query and one ranked fix with its computed confidence, then follows IDs into records, troubleshoots and reads the evaluation of each query.
FIRST VIEWPORT: Rail with nav and live station status; report composer with presets and a cobalt Analyze; then a full-width verdict field, a one-line query evaluation and the ranked fix.
FORM: Analog Forecast Desk, grounded candidate 5 of 7, seed b3f75bba.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${archivo.variable} ${geistMono.variable} antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <div hidden dangerouslySetInnerHTML={{ __html: `<!--${CONTRACT}-->` }} />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
