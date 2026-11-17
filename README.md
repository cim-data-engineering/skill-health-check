# health-check

A PEAK skill that renders one health check for one site in chat: an equipment health snapshot, an indoor environment health snapshot, the assignee leaderboard, or equipment run hours.

## Install

1. Connect PEAK to your AI assistant, which the skill needs: [PEAK AI Connector (MCP)](https://support.cim.io/en/articles/14883828-peak-ai-connector-mcp)
2. On this page, click **Code > Download ZIP**
3. Upload that one zip as a skill: Claude **Customize > Skills**, ChatGPT **Plugins > Skills**, Copilot Studio **Build > Skills**

## Use

```
/health-check <site name>
/health-check <check> <site name>
```

Without a check, the skill asks which:

| Check | Renders |
| --- | --- |
| Equipment health snapshot | Health by equipment type, monthly |
| Indoor environment health snapshot | Thermal comfort by level, monthly |
| Assignee leaderboard | Who closed the work, last 90 days |
| Equipment run hours | When plant runs vs when the building is occupied, last full week |

## Releases

- **13 Aug 2026**: First release. Equipment health snapshot, indoor environment health snapshot and assignee leaderboard
- **18 Aug 2026**: Equipment run hours
- **6 Oct 2026**: Equipment run hours as a weekly chart, one row per unit, each linked to its PEAK chart
- **17 Nov 2026**: Equipment run hours drawn from the metadata listed for each equipment type, using the one with the fewest running hours
