import { ScrollScrubEngine } from "@/components/ScrollScrubEngine";
import { SITE_DATA } from "@/lib/site-data.generated";

export default function Page() {
  return (
    <main>
      <ScrollScrubEngine siteData={SITE_DATA} />
    </main>
  );
}
