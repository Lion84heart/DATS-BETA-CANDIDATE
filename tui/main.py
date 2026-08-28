#!/usr/bin/env python3
"""
DATS Terminal User Interface (TUI)
Professional trading terminal in the terminal.

Usage:
    python3 tui/main.py

Requirements:
    pip install textual requests
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, Footer
from textual.binding import Binding

API_BASE = os.environ.get("DATS_API_URL", "http://localhost:8000")


class TickerBar(Static):
    """Top ticker bar with scrolling symbols."""
    
    def compose(self) -> ComposeResult:
        tickers = [
            ("AAPL", 182.50, 1.25, 0.69), ("MSFT", 335.80, 2.10, 0.63),
            ("GOOGL", 128.40, -0.85, -0.66), ("TSLA", 255.30, 5.20, 2.08),
            ("NVDA", 465.00, 8.40, 1.84), ("AMZN", 158.00, -1.20, -0.75),
            ("META", 510.00, 3.50, 0.69), ("AMD", 142.00, 2.80, 2.01),
        ]
        parts = []
        for sym, price, chg, pct in tickers:
            color = "#00c851" if chg >= 0 else "#ff4444"
            arrow = "▲" if chg >= 0 else "▼"
            parts.append(f"[b]{sym}[/b] {price:.2f} [{color}]{arrow}{abs(chg):.2f}({abs(pct):.2f}%)[/{color}]")
        yield Static("  |  ".join(parts), id="ticker-content")


class StatusBar(Static):
    """Top status bar."""
    
    def compose(self) -> ComposeResult:
        with Horizontal(id="status-row"):
            yield Static("[b #00ffff]DATS TERMINAL[/b #00ffff]  [dim]v1.0.0-beta[/dim]  [b #00c851]LIVE[/b #00c851]", id="status-left")
            yield Static(
                "PORTFOLIO: [b #00ffff]$128,450.50[/b #00ffff]  P&L: [b #00c851]+$2,340.80[/b #00c851]  BP: [b]$95,000[/b]  |  [b #ffbb33]DEMO MODE[/b #ffbb33]",
                id="status-right"
            )


class WatchlistPanel(Static):
    """Watchlist panel."""
    
    def compose(self) -> ComposeResult:
        yield Static("[b dim]━━ WATCHLIST [F1] ━━[/b dim]", id="watchlist-title")
        
        watchlist = [
            ("AAPL", 182.50, 0.69, "45.2M"), ("MSFT", 335.80, 0.63, "22.1M"),
            ("GOOGL", 128.40, -0.66, "18.7M"), ("TSLA", 255.30, 2.08, "98.3M"),
            ("NVDA", 465.00, 1.84, "52.1M"), ("AMZN", 158.00, -0.75, "31.4M"),
            ("META", 510.00, 0.69, "15.2M"), ("AMD", 142.00, 2.01, "28.9M"),
            ("NFLX", 685.20, 1.12, "8.3M"), ("SPY", 445.30, 0.45, "52.8M"),
            ("QQQ", 378.50, 0.62, "28.4M"), ("IWM", 198.40, -0.23, "18.1M"),
        ]
        
        lines = ["[dim]SYM       LAST      CHG%       VOL[/dim]"]
        for sym, price, pct, vol in watchlist:
            color = "#00c851" if pct >= 0 else "#ff4444"
            arrow = "▲" if pct >= 0 else "▼"
            lines.append(f"[b]{sym:8}[/b]  {price:8.2f}  [{color}]{arrow}{abs(pct):5.2f}%[/{color}]  {vol:>8}")
        
        yield Static("\n".join(lines), id="watchlist-content")


class OrderBookPanel(Static):
    """Level 2 order book."""
    
    def compose(self) -> ComposeResult:
        yield Static("[b dim]━━ ORDER BOOK L2 [F3] ━━[/b dim]", id="book-title")
        lines = [
            "[dim]   BID SZ     BID      ASK     ASK SZ[/dim]",
            "",
            "       ────      ────   [b #ff4444]183.20[/b #ff4444]     2,450",
            "       ────      ────   [b #ff4444]183.15[/b #ff4444]     1,820",
            "       ────      ────   [b #ff4444]183.10[/b #ff4444]     3,100",
            "       ────      ────   [b #ff4444]183.05[/b #ff4444]     1,500",
            "       ────      ────   [b #ff4444]183.00[/b #ff4444]     4,200",
            "",
            "[dim]              SPREAD: 0.05[/dim]",
            "",
            " 3,800   [b #00c851]182.95[/b #00c851]   ────      ────",
            " 2,100   [b #00c851]182.90[/b #00c851]   ────      ────",
            " 5,400   [b #00c851]182.85[/b #00c851]   ────      ────",
            " 1,900   [b #00c851]182.80[/b #00c851]   ────      ────",
            " 6,200   [b #00c851]182.75[/b #00c851]   ────      ────",
        ]
        yield Static("\n".join(lines), id="book-content")


class ChartPanel(Static):
    """Chart panel with ASCII art."""
    
    def compose(self) -> ComposeResult:
        yield Static("[b dim]━━ AAPL [F2] ━━[/b dim]  [b #00c851]▲ +1.25 (+0.69%)[/b #00c851]", id="chart-title")
        chart = """
[b #00ffff] 183.80[/b #00ffff] ┤                                          ╭───────
[b #00ffff] 183.00[/b #00ffff] ┤                              ╭─────╯
[b #00ffff] 182.50[/b #00ffff] ┤                    ╭─────╮  ╭──╯          [b]← Current[/b]
[b #00ffff] 181.80[/b #00ffff] ┤           ╭──────╯      ╰──╯
[b #00ffff] 181.00[/b #00ffff] ┤    ╭────╯
[b #00ffff] 180.20[/b #00ffff] ┤╭───╯
           └┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬
           09:30 09:45 10:00 10:15 10:30 10:45 11:00 11:15 11:30

[dim]O[/dim]:181.25  [dim]H[/dim]:[b #00c851]183.80[/b #00c851]  [dim]L[/dim]:[b #ff4444]180.90[/b #ff4444]  [dim]C[/dim]:182.50  [dim]Vol[/dim]:45.2M  [dim]VWAP[/dim]:182.10
        """
        yield Static(chart, id="chart-content")


class PositionsPanel(Static):
    """Positions panel."""
    
    def compose(self) -> ComposeResult:
        yield Static("[b dim]━━ POSITIONS [F5] ━━[/b dim]", id="pos-title")
        lines = [
            "[dim]SYM    SIDE  QTY  AVG      MARK     DAY P&L      TOTAL P&L[/dim]",
            "",
            "[b]AAPL[/b]  LONG  50   175.20   182.50   [b #00c851]+$365.00[/b #00c851]   [b #00c851]+$365.00[/b #00c851]",
            "[b]MSFT[/b]  LONG  30   320.00   335.80   [b #00c851]+$474.00[/b #00c851]   [b #00c851]+$474.00[/b #00c851]",
            "[b]GOOGL[/b] LONG  25   130.00   128.40   [b #ff4444]-$40.00[/b #ff4444]    [b #ff4444]-$40.00[/b #ff4444]",
            "[b]TSLA[/b]  LONG  20   240.00   255.30   [b #00c851]+$306.00[/b #00c851]   [b #00c851]+$306.00[/b #00c851]",
            "",
            "[dim]─────────────────────────────────────────────────────────────[/dim]",
            "TOTAL                          [b #00c851]+$1,105.00[/b #00c851]   [b #00c851]+$1,105.00[/b #00c851]",
        ]
        yield Static("\n".join(lines), id="pos-content")


class OrdersPanel(Static):
    """Orders panel."""
    
    def compose(self) -> ComposeResult:
        yield Static("[b dim]━━ ORDERS [F6] ━━[/b dim]", id="ord-title")
        lines = [
            "[dim]ID       TIME     SYM    SIDE   TYPE  QTY   PRICE    STATUS[/dim]",
            "",
            "[dim]ORD-001[/dim] 09:30:15 [b]AAPL[/b]   [b #00c851]BUY[/b #00c851]   MKT   50    182.50   [b #00c851]FILLED[/b #00c851]",
            "[dim]ORD-002[/dim] 09:35:22 [b]MSFT[/b]   [b #00c851]BUY[/b #00c851]   LMT   30    320.00   [b #00c851]FILLED[/b #00c851]",
            "[dim]ORD-003[/dim] 10:15:08 [b]GOOGL[/b]  [b #00c851]BUY[/b #00c851]   MKT   25    130.00   [b #00c851]FILLED[/b #00c851]",
            "[dim]ORD-004[/dim] 11:00:45 [b]TSLA[/b]   [b #00c851]BUY[/b #00c851]   MKT   20    240.00   [b #00c851]FILLED[/b #00c851]",
            "[dim]ORD-005[/dim] 14:30:10 [b]NVDA[/b]   [b #ff4444]SELL[/b #ff4444]  LMT   15    465.00   [b #00c851]FILLED[/b #00c851]",
        ]
        yield Static("\n".join(lines), id="ord-content")


class AIPanel(Static):
    """AI signals panel."""
    
    def compose(self) -> ComposeResult:
        yield Static("[b dim]━━ AI SIGNALS [F7] ━━[/b dim]", id="ai-title")
        lines = [
            "[dim]SYM   SIGNAL  CONF   STRATEGY           TARGET   STOP[/dim]",
            "",
            "[b]AMD[/b]   [b #00c851]BUY[/b #00c851]     82%    Momentum Alpha     $155     $132",
            "[b]AAPL[/b]  [b #00c851]BUY[/b #00c851]     87%    Momentum Alpha     In pos   Hold",
            "[b]NVDA[/b]  [b #ff4444]SELL[/b #ff4444]    78%    Trend Following    $480     $450",
            "",
            "[dim]Latest: AMD BUY triggered at 13:15. RSI=62, MACD bullish.[/dim]",
        ]
        yield Static("\n".join(lines), id="ai-content")


class RiskPanel(Static):
    """Risk metrics panel."""
    
    def compose(self) -> ComposeResult:
        yield Static("[b dim]━━ RISK METRICS [F8] ━━[/b dim]", id="risk-title")
        lines = [
            "MAX DRAWDOWN  [b #00c851]2.4%[/b #00c851]    [dim]████████████████░░░░░░░░[/dim]",
            "DAILY LOSS    [b #00c851]1.8%[/b #00c851]    [dim]████████████░░░░░░░░░░░░[/dim]",
            "KILL SWITCH   [b #ffbb33]ARMED[/b #ffbb33]   [dim]●[/dim]",
            "MARGIN USED   [b]5.0%[/b]     [dim]██░░░░░░░░░░░░░░░░░░░░░░[/dim]",
            "",
            "[dim]Consecutive losses: 0/5[/dim]",
            "[dim]Cooldown: 300s remaining[/dim]",
        ]
        yield Static("\n".join(lines), id="risk-content")


class TimeSalesPanel(Static):
    """Time & Sales panel."""
    
    def compose(self) -> ComposeResult:
        yield Static("[b dim]━━ TIME & SALES [F4] ━━[/b dim]", id="tns-title")
        lines = [
            "[dim]TIME     PRICE     SIZE     EX[/dim]",
            "",
            "09:30:15  182.50    [b]500[/b]      [b #00c851]@ASK[/b #00c851]",
            "09:30:12  182.48    200      [b #ff4444]@BID[/b #ff4444]",
            "09:30:10  182.49    [b]1,200[/b]    [b #00c851]@ASK[/b #00c851]",
            "09:30:08  182.47    800      [b #ff4444]@BID[/b #ff4444]",
            "09:30:05  182.48    350      [b #00c851]@ASK[/b #00c851]",
            "09:30:02  182.46    600      [b #ff4444]@BID[/b #ff4444]",
            "09:30:00  182.47    [b]2,100[/b]    [b #00c851]@ASK[/b #00c851]",
        ]
        yield Static("\n".join(lines), id="tns-content")


class AccountBar(Static):
    """Bottom account bar."""
    
    def compose(self) -> ComposeResult:
        yield Static(
            "ACCT: [b #00ffff]DEMO-001[/b #00ffff]  |  EQ: [b]$128,450.50[/b]  |  BP: [b #00c851]$95,000.00[/b #00c851]  |  "
            "MARGIN: [b]$14,082[/b]  |  DAY P&L: [b #00c851]+$2,340.80[/b #00c851]  |  "
            "TOTAL P&L: [b #00c851]+$28,450.50[/b #00c851]  |  OPEN: [b]4[/b]  |  [b #ffbb33]DEMO MODE[/b #ffbb33]",
            id="account-content"
        )


class DATSTerminal(App):
    """DATS Professional Trading Terminal TUI."""
    
    CSS = """
    Screen {
        background: #000000;
        color: #c8c8c8;
    }
    
    #ticker-content {
        height: 1;
        background: #0a0a0a;
        color: #c8c8c8;
        content-align: left middle;
        padding: 0 1;
    }
    
    #status-row {
        height: 1;
        background: #0a0a0a;
        border-bottom: solid #1a1a1a;
    }
    
    #status-left {
        width: auto;
        content-align: left middle;
        padding: 0 1;
    }
    
    #status-right {
        width: auto;
        content-align: right middle;
        padding: 0 1;
    }
    
    #watchlist-title, #book-title, #chart-title, #pos-title, #ord-title, #ai-title, #risk-title, #tns-title {
        height: 1;
        background: #111111;
        color: #666666;
        padding: 0 1;
        content-align: left middle;
    }
    
    #watchlist-content, #book-content, #chart-content, #pos-content, #ord-content, #ai-content, #risk-content, #tns-content {
        padding: 0 1;
        height: 1fr;
        overflow: auto;
    }
    
    #account-content {
        height: 1;
        background: #0a0a0a;
        border-top: solid #1a1a1a;
        content-align: left middle;
        padding: 0 1;
    }
    
    .left-col {
        width: 30;
        border-right: solid #1a1a1a;
    }
    
    .right-col {
        width: 30;
        border-left: solid #1a1a1a;
    }
    
    .center-col {
        width: 1fr;
    }
    
    .bottom-row {
        height: 12;
        border-top: solid #1a1a1a;
    }
    
    Footer {
        background: #0a0a0a;
        color: #666666;
    }
    
    Footer > .footer--highlight {
        background: #1a1a1a;
        color: #00ffff;
    }
    
    Footer > .footer--key {
        background: #1a1a1a;
        color: #c8c8c8;
    }
    """
    
    BINDINGS = [
        Binding("1", "watchlist", "Watchlist"),
        Binding("2", "chart", "Chart"),
        Binding("3", "book", "Book"),
        Binding("4", "tns", "T&S"),
        Binding("5", "positions", "Positions"),
        Binding("6", "orders", "Orders"),
        Binding("7", "ai", "AI"),
        Binding("8", "risk", "Risk"),
        Binding("b", "buy", "Buy"),
        Binding("s", "sell", "Sell"),
        Binding("q", "quit", "Quit"),
        Binding("?", "help", "Help"),
    ]
    
    def compose(self) -> ComposeResult:
        yield TickerBar()
        yield StatusBar()
        
        with Horizontal(id="main-layout"):
            with Vertical(classes="left-col"):
                yield WatchlistPanel()
            
            with Vertical(classes="center-col"):
                with Horizontal():
                    yield ChartPanel()
                    yield OrderBookPanel()
                
                with Horizontal(classes="bottom-row"):
                    yield PositionsPanel()
                    yield TimeSalesPanel()
            
            with Vertical(classes="right-col"):
                yield AIPanel()
                yield RiskPanel()
        
        yield AccountBar()
        yield Footer()
    
    def action_watchlist(self):
        self.notify("Watchlist [1] - Focus watchlist panel", timeout=2)
    
    def action_chart(self):
        self.notify("Chart [2] - AAPL intraday", timeout=2)
    
    def action_book(self):
        self.notify("Order Book [3] - L2 market depth", timeout=2)
    
    def action_tns(self):
        self.notify("Time & Sales [4] - Recent trades", timeout=2)
    
    def action_positions(self):
        self.notify("Positions [5] - 4 open positions", timeout=2)
    
    def action_orders(self):
        self.notify("Orders [6] - 5 filled orders", timeout=2)
    
    def action_ai(self):
        self.notify("AI Signals [7] - 3 active signals", timeout=2)
    
    def action_risk(self):
        self.notify("Risk [8] - Normal, Kill Switch Armed", timeout=2)
    
    def action_buy(self):
        self.notify("BUY order entry (demo mode)", severity="information", timeout=2)
    
    def action_sell(self):
        self.notify("SELL order entry (demo mode)", severity="warning", timeout=2)
    
    def action_help(self):
        help_text = """
[b]DATS Terminal Keyboard Shortcuts[/b]

[b]Navigation:[/b]
  [b]1[/b]  Watchlist    [b]5[/b]  Positions
  [b]2[/b]  Chart        [b]6[/b]  Orders
  [b]3[/b]  Order Book   [b]7[/b]  AI Signals
  [b]4[/b]  Time & Sales [b]8[/b]  Risk Metrics

[b]Trading:[/b]
  [b]B[/b]  Buy Order    [b]S[/b]  Sell Order

[b]General:[/b]
  [b]Q[/b]  Quit         [b]?[/b]  This Help

[b #ffbb33]DEMO MODE ACTIVE[/b #ffbb33]
        """
        self.notify(help_text, timeout=10)
    
    def on_mount(self) -> None:
        self.title = "DATS Terminal"
        self.sub_title = "Beta v1.0.0"
        self.notify("DATS Terminal loaded. Press ? for help.", timeout=3)


if __name__ == "__main__":
    app = DATSTerminal()
    app.run()
