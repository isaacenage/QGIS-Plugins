import type { Metadata } from "next";
import { TPPH } from "@/lib/site";
import { TpphHeader } from "@/components/tpph-header";
import { TpphFooter } from "@/components/tpph-footer";

// The Title Plotter PH section. Root layout owns <html>/<body>/fonts; this
// nested layout adds the plugin's own chrome (header + footer) and its title
// scope, so the hub at "/" stays free of plugin-branded navigation.
export const metadata: Metadata = {
  title: {
    default: `${TPPH.name} — ${TPPH.tagline}`,
    template: `%s · ${TPPH.name}`,
  },
  description:
    "A free, open-source QGIS plugin that plots Philippine land titles from their bearing-and-distance technical descriptions — tie-point based, with live preview, optional AI OCR, and PRS92/WGS84 support. No GIS background needed.",
};

export default function TitlePlotterSectionLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <>
      <TpphHeader />
      <main>{children}</main>
      <TpphFooter />
    </>
  );
}
