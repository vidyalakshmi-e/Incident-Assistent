import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex max-w-[60ch] flex-col gap-3 pt-10">
      <h1 className="display text-[29px] font-bold text-ink">Nothing charted here</h1>
      <p className="text-[15.5px] text-ink-2">This page does not exist. The desk starts at the Incident Assistant.</p>
      <Link href="/assistant" className="text-[15px] font-semibold text-cobalt hover:underline">
        Open the Incident Assistant
      </Link>
    </div>
  );
}
