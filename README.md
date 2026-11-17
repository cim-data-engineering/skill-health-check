# health-check

A PEAK skill that renders a health check for one site in chat: equipment health by equipment type, indoor environment by level, the assignee leaderboard, or equipment run hours against the site's working hours.

## Install

1. Connect PEAK to your AI assistant, which the skill needs: [PEAK AI Connector (MCP)](https://support.cim.io/en/articles/14883828-peak-ai-connector-mcp)
2. On this page, click **Code > Download ZIP**
3. Upload that one zip as a skill: Claude **Customize > Skills**, ChatGPT **Plugins > Skills**, Copilot Studio **Build > Skills**

## Use

```
/health-check <site name>
/health-check <check> <site name>
```

`<check>` is `equipment`, `indoor environment`, `leaderboard` or `run hours`. Without one, the skill asks which.

## Releases

- **13 Aug 2026**: First release. Equipment health, indoor environment and assignee leaderboard
- **18 Aug 2026**: Equipment run hours
- **6 Oct 2026**: Run hours as a weekly chart, one row per unit, each linked to its PEAK chart
- **17 Nov 2026**: Run hours drawn from the metadata listed for each equipment type, using the one with the fewest running hours
