from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

try:
    from .browser_session import build_session_config, launch_persistent_context, save_evidence
    from .site_adapters import adapter_for_url
except ImportError:
    from browser_session import build_session_config, launch_persistent_context, save_evidence
    from site_adapters import adapter_for_url


async def run(args: argparse.Namespace) -> int:
    adapter = adapter_for_url(args.url)
    site_name = args.site_name or (adapter.name if adapter else None)
    config = build_session_config(args.url, root=args.root, site_name=site_name, headless=args.headless)
    playwright, context = await launch_persistent_context(config)
    try:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout_ms)
        await page.wait_for_timeout(args.settle_ms)
        html = await page.content()
        screenshot = await page.screenshot(full_page=True)
        evidence = save_evidence(
            config=config,
            job_key=args.job_key,
            url=args.url,
            stage=args.stage,
            reason=args.reason,
            html=html,
            screenshot_bytes=screenshot,
            metadata={
                "adapter": adapter.name if adapter else None,
                "title": await page.title(),
                "current_url": page.url,
                "manual_gate_expected": args.manual_gate,
            },
        )
        print(f"Evidence saved: {evidence.metadata_path}")
        if args.keep_open:
            print("Browser remains open. Complete the human gate, then press Enter here to close.")
            input()
        return 0
    finally:
        await context.close()
        await playwright.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Open a job application URL in a persistent browser profile and save evidence.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--job-key", required=True)
    parser.add_argument("--stage", default="application-gate")
    parser.add_argument("--reason", default="manual submission gate")
    parser.add_argument("--site-name")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--timeout-ms", type=int, default=45000)
    parser.add_argument("--settle-ms", type=int, default=2500)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--keep-open", action="store_true")
    parser.add_argument("--manual-gate", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
