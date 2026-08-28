import { PackageSearch, ShieldCheck } from "lucide-react";

export default function MarketplacePreviewPage() {
  return <div className="mission-page"><header className="mission-heading"><div><p className="eyebrow">Preview surface</p><h1>Marketplace</h1><p>A verified distribution channel for role, skill, tool, and automation packages is planned. Installation is disabled until signing, capability disclosure, and permission review are implemented.</p></div><span className="badge amber">Preview</span></header><section className="panel empty-state min-h-[420px]"><div><PackageSearch size={30} className="mx-auto mb-4" style={{ color: "var(--blue-4)" }} /><h2 className="text-base font-semibold">No pretend installs</h2><p className="mt-2 max-w-lg" style={{ color: "var(--fg-muted)" }}>The catalog will remain empty until packages can be verified and installed safely.</p><span className="signal-chip mt-5"><ShieldCheck size={12} /> Signing required before launch</span></div></section></div>;
}
