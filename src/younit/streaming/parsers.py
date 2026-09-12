"""Field-name definitions for all five Lightstreamer stream types.

Each constant is the list of fields to request from Lightstreamer.
These match exactly what the streaming guide documents.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# SymbolStatistics — item prefix: sy{stockId}  mode: MERGE
# ---------------------------------------------------------------------------

SYMBOL_FIELDS: list[str] = [
    "key",
    "m_SymbolID",
    "m_ShortName",
    "m_StockName",
    "m_BourseCode",
    "m_ISIN",
    "m_Reuters",
    "m_SectorName",
    "m_CurrencyID",
    "m_Currency",
    "m_MessageSequence",
    "m_LastUpdated",
    "Actions",
    "m_LastTradePrice",
    "m_LastTradeVolume",
    "m_OpenPrice",
    "m_ClosePrice",
    "m_DailyHighPrice",
    "m_DailyLowPrice",
    "m_ReferencePrice",
    "m_adjustedYestClose",
    "m_MinPrice",
    "m_MaxPrice",
    "m_BidPrice",
    "m_BidVol",
    "m_AskPrice",
    "m_AskVol",
    "m_BidBook",
    "m_AskBook",
    "m_TotalBids",
    "m_TotalAsks",
    "m_TradedVolume",
    "m_TradedValue",
    "m_TradesCount",
    "m_Change",
    "m_ChangeDir",
    "m_PercentChange",
    "m_TOP",
    "m_TOV",
    "m_Wk52HighPrice",
    "m_Wk52LowPrice",
    "m_ListedShares",
    "ListedShares",
    "m_MarketCap",
    "m_SymbolStatusID",
    "m_SymbolStatusUI",
    "m_HasBulletin",
    "m_HasBulletinUI",
    "m_DataFeedSubscribtionStatus",
]

# ---------------------------------------------------------------------------
# IndexStatistics — item prefix: ix{indexId}  mode: MERGE
# ---------------------------------------------------------------------------

INDEX_FIELDS: list[str] = [
    "key",
    "m_IndexID",
    "m_IndexName",
    "m_EnglishName",
    "m_IndexType",
    "m_MarketName",
    "m_MarketID",
    "m_IndexValue",
    "m_IndexOpen",
    "m_IndexClose",
    "m_IndexHigh",
    "m_IndexLow",
    "m_IndexWk52High",
    "m_IndexWk52Low",
    "m_NetChange",
    "m_PrecentChange",
    "m_ChangeDir",
    "m_TradedValue",
    "m_TradedVolume",
]

# ---------------------------------------------------------------------------
# MarketStatistics — item prefix: mk{marketId}  mode: MERGE
# ---------------------------------------------------------------------------

MARKET_FIELDS: list[str] = [
    "m_MessageSequence",
    "MarketTime",
    "m_TradedValue",
    "m_TradedVolume",
    "m_TradesCount",
    "m_EnglishName",
    "m_ArabicName",
    "m_MarketID",
    "m_TradedSymCount",
    "m_AdvTradesCount",
    "m_DclnTradesCount",
    "m_UnchgTradesCount",
    "m_MarketStatus",
    "m_OpenTime",
    "m_CloseTime",
]

# ---------------------------------------------------------------------------
# SecurityTrades — item prefix: ts{stockId}  mode: COMMAND
# ---------------------------------------------------------------------------

TRADE_FIELDS: list[str] = [
    "key",
    "command",
    "m_MessageSequence",
    "m_SymbolID",
    "m_MarektID",  # Note: typo in the API — "Marekt" not "Market"
    "m_TicketNumber",
    "m_TradePrice",
    "m_TradeVolume",
    "m_LastUpdated",
    "m_LastUpdatedField",
    "m_PriceChgFromClose",
    "m_PercentChgFromClose",
    "m_PriceChgFromAvg",
    "TransactionType",
    "TransactionTypeField",
]

# ---------------------------------------------------------------------------
# ActiveOrders — item prefix: po{clientAccountId}  mode: COMMAND
# ---------------------------------------------------------------------------

ORDER_FIELDS: list[str] = [
    "key",
    "command",
    "m_MessageSequence",
    "m_SymbolID",
    "m_OrderNumber",
    "m_OrderDate",
    "m_OrderPrice",
    "m_OrderType",
    "m_OrderQuantity",
    "m_OrderExecQuantity",
    "m_OrderRemainingQuantity",
    "m_OrderAvgPrice",
    "m_OrderPlacedBy",
    "m_OrderStatus",
    "m_OrderTypeUI",
    "m_OrderPlacedByUI",
    "m_OrderStatusUI",
    "m_OrderFixStatus",
    "m_ExpireDate",
    "m_IsOrderLocked",
    "m_AccOfficerID",
    "m_CompanyCode",
    "m_MarketID",
    "m_ClientAccProfileID",
]
