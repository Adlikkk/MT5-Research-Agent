//+------------------------------------------------------------------+
//| US30_Demo_Breakout.mq5
//|
//| ============================ DEMO EA ============================
//| This is a DEMONSTRATION Expert Advisor shipped as a safe example.
//| It is produced by the MT5 Research Agent EA Lab safe-by-default
//| template (see `mt5-research-agent create-ea-from-prompt`).
//|
//| Strategy Tester research only. No live trading is intended.
//| Safety defaults: one position max, no martingale, no grid,
//| explicit risk controls, session filter, spread filter.
//|
//| It is NOT a profitable strategy and carries NO guarantee of any
//| kind. Use it only to see the research workflow end to end.
//| =================================================================
//+------------------------------------------------------------------+
#property strict
#property version   "1.0"
#property description "DEMO EA from MT5 Research Agent EA Lab (Strategy Tester research only; no guarantees)."

#include <Trade/Trade.mqh>

// All meaningful values are inputs so the research loop can tune them.
input double InpLots            = 0.10;  // Fixed lot size (used when InpRiskPercent == 0)
input double InpRiskPercent     = 0.0;   // Risk percent per trade (0 = use fixed lot)
input int    InpATRPeriod       = 14;    // ATR period for stop sizing
input double InpSL_ATR_Mult     = 1.5;   // Stop loss = ATR * this multiple
input double InpTP_R            = 2.0;   // Take profit as a multiple of risk (R)
input int    InpBreakoutBars    = 20;    // Lookback bars for breakout high/low
input int    InpSessionStartHour= 8;     // Session start hour (server time)
input int    InpSessionEndHour  = 20;    // Session end hour (server time)
input int    InpMaxSpreadPoints = 50;    // Skip trades above this spread (points)
input int    InpMaxPositions    = 1;     // Maximum concurrent positions (>=1)
input bool   InpAllowWednesday  = true;  // Allow new trades on Wednesday
input long   InpMagic           = 990001;// Magic number

CTrade   trade;
int      atrHandle = INVALID_HANDLE;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpMaxPositions < 1)
     {
      Print("InpMaxPositions must be >= 1; refusing unsafe stacking config.");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(InpSL_ATR_Mult <= 0.0 || InpTP_R <= 0.0)
     {
      Print("Stop and take-profit multiples must be positive.");
      return(INIT_PARAMETERS_INCORRECT);
     }
   atrHandle = iATR(_Symbol, _Period, InpATRPeriod);
   if(atrHandle == INVALID_HANDLE)
     {
      Print("Failed to create ATR handle.");
      return(INIT_FAILED);
     }
   trade.SetExpertMagicNumber(InpMagic);
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(atrHandle != INVALID_HANDLE)
      IndicatorRelease(atrHandle);
  }

//+------------------------------------------------------------------+
int CountOwnPositions()
  {
   int total = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) == InpMagic &&
         PositionGetString(POSITION_SYMBOL) == _Symbol)
         total++;
     }
   return(total);
  }

//+------------------------------------------------------------------+
bool InSession()
  {
   MqlDateTime now;
   TimeToStruct(TimeCurrent(), now);
   if(!InpAllowWednesday && now.day_of_week == 3)
      return(false);
   if(InpSessionStartHour <= InpSessionEndHour)
      return(now.hour >= InpSessionStartHour && now.hour < InpSessionEndHour);
   return(now.hour >= InpSessionStartHour || now.hour < InpSessionEndHour);
  }

//+------------------------------------------------------------------+
bool SpreadOk()
  {
   long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   return(spread <= (long)InpMaxSpreadPoints);
  }

//+------------------------------------------------------------------+
double LotSize(double stopDistance)
  {
   if(InpRiskPercent <= 0.0 || stopDistance <= 0.0)
      return(InpLots);
   double balance   = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskMoney = balance * (InpRiskPercent / 100.0);
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickValue <= 0.0 || tickSize <= 0.0)
      return(InpLots);
   double valuePerPoint = tickValue / tickSize;
   double lots = riskMoney / (stopDistance * valuePerPoint);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double step   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step > 0.0)
      lots = MathFloor(lots / step) * step;
   return(MathMax(minLot, lots));
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   // One decision per new bar.
   static datetime lastBar = 0;
   datetime currentBar = iTime(_Symbol, _Period, 0);
   if(currentBar == lastBar)
      return;
   lastBar = currentBar;

   if(CountOwnPositions() >= InpMaxPositions)
      return;
   if(!InSession() || !SpreadOk())
      return;

   double atr[];
   if(CopyBuffer(atrHandle, 0, 1, 1, atr) <= 0)
      return;
   double atrValue = atr[0];
   if(atrValue <= 0.0)
      return;

   double highest = iHigh(_Symbol, _Period, iHighest(_Symbol, _Period, MODE_HIGH, InpBreakoutBars, 1));
   double lowest  = iLow(_Symbol, _Period, iLowest(_Symbol, _Period, MODE_LOW, InpBreakoutBars, 1));
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   double stopDistance = atrValue * InpSL_ATR_Mult;

   if(ask > highest)
     {
      double sl = ask - stopDistance;
      double tp = ask + stopDistance * InpTP_R;
      trade.Buy(LotSize(stopDistance), _Symbol, ask, sl, tp, "demo-breakout");
     }
   else if(bid < lowest)
     {
      double sl = bid + stopDistance;
      double tp = bid - stopDistance * InpTP_R;
      trade.Sell(LotSize(stopDistance), _Symbol, bid, sl, tp, "demo-breakout");
     }
  }
//+------------------------------------------------------------------+
