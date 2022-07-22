"""
Rebalance current portfolio to equal weight,using IBKR EWrapper callbacks and EClient requests
"""
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
import threading
import time

class TradingApp(EWrapper, EClient):
    def __init__(self,cash = 0.001):
        EClient.__init__(self,self)
        self.cash = cash
        
        self.connect("127.0.0.1",7497,clientId=2)
        # starting a separate daemon thread to execute the websocket connection
        conn_thread = threading.Thread(target=self.websocket_conn,daemon=True)
        conn_thread.start()
        time.sleep(1)   # some latency added to ensure that the connection is established
        
        #cancel all pending orders before rebalance
        self.reqGlobalCancel()
        #position information
        self.pos = {}
        self.symbols = []
        #account summary
        self.account_info = {}
        #last close trade price
        self.ltp = {}

        #sell and buy dict
        self.sell = {}
        self.buy = {}
        
        #events for requests
        self.hist_event = threading.Event()
        self.pos_event = threading.Event()
        self.acc_event = threading.Event()
    
    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)
        self.nextValidOrderId = orderId
        
    def historicalData(self, reqId, bar):
        self.ltp[self.symbols[reqId]] = bar.close
        
    def historicalDataEnd(self, reqId: int, start: str, end: str):
        super().historicalDataEnd(reqId, start, end)
        self.hist_event.set()
        
    def position(self, account, contract, position, avgCost):
        super().position(account, contract, position, avgCost)
        if int(position) != 0:
            self.pos[contract.symbol] = int(position)
            if contract.symbol not in self.symbols:
                self.symbols.append(contract.symbol)
    
    def positionEnd(self):
        super().positionEnd()
        self.pos_event.set()
        
    def accountSummary(self, reqId: int, account: str, tag: str, value: str,currency: str):
        super().accountSummary(reqId, account, tag, value, currency)
        if tag == "TotalCashBalance" or tag == "StockMarketValue":
            self.account_info[tag] = value
    
    def accountSummaryEnd(self, reqId: int):
        super().accountSummaryEnd(reqId)
        self.acc_event.set()
           
    def requestInfo(self):
        self.reqPositions()   #request current positions information
        self.pos_event.wait()
        self.reqAccountSummary(self.nextValidOrderId,"All","$LEDGER:USD")   #request account information
        self.acc_event.wait()
        
    def reAllocate(self):
        self.requestInfo()
        
        #calculate new asset allocation
        TotalEquity = float(self.account_info["TotalCashBalance"]) + float(self.account_info["StockMarketValue"])
        asset_weight = (1 - self.cash) / len(self.pos)
        new_alloc = int(TotalEquity * asset_weight)
        
        #request latest trade price for each symbol
        for s in self.symbols:
            self.hist_event.clear()
            self.reqHistoricalData(self.symbols.index(s),self.StockContract(s),
                                   endDateTime='',
                                   durationStr='1 D',
                                   barSizeSetting='1 day',
                                   whatToShow='ADJUSTED_LAST',
                                   useRTH=1,
                                   formatDate=1,
                                   keepUpToDate=0,
                                   chartOptions=[])
            self.hist_event.wait()  # wait until current historical data request completes

        #calculate selling and buying amount
        for s in self.symbols:
            upd_pos = int(new_alloc/self.ltp[s])
            if upd_pos > self.pos[s]:
                self.buy[s] = int(upd_pos - self.pos[s])
            elif upd_pos < self.pos[s]:
                self.sell[s] = int(self.pos[s] - upd_pos)
            else:
                continue
        print("sell: ",self.sell,"buy: ",self.buy)
    
    def placeUpdOrder(self):
        order_id = self.nextValidOrderId
        for k,v in self.sell.items():
            if v == 0:
                continue
            self.placeOrder(order_id,self.StockContract(k),self.StockMktOrder(v,"SELL"))
            order_id += 1
        
        for k,v in self.buy.items():
            if v == 0:
                continue
            self.placeOrder(order_id,self.StockContract(k),self.StockMktOrder(v,"BUY"))
            order_id += 1
        
    def StockMktOrder(self,quantity,direction): #stock market order
        order = Order()
        order.action = direction
        order.orderType = "MKT"
        order.totalQuantity = quantity
        return order
    
    def StockContract(self,symbol,sec_type = "STK",currency = "USD",exchange = "ISLAND"):   #stock contract
        contract = Contract()
        contract.symbol = symbol
        contract.secType = sec_type
        contract.currency = currency
        contract.exchange = exchange
        return contract  
    
    def sellStock(self,symbol): # sell one single stock
        self.requestInfo()
        if symbol not in self.pos or self.pos[symbol] == 0:
            return
        self.placeOrder(self.nextValidOrderId,self.StockContract(symbol),self.StockMktOrder(int(self.pos[symbol]),"SELL"))
        
    def buyStock(self,symbol,quantity):  # buy one single stock
        self.placeOrder(self.nextValidOrderId,self.StockContract(symbol),self.StockMktOrder(quantity,"BUY"))
        
    def websocket_conn(self):
        self.run()
         
if __name__ == "__main__":
    app = TradingApp()         
    # app.reAllocate()
    # print(app.pos)
    # print("account information: ",app.account_info)
    # app.placeUpdOrder()
    app.buyStock("TSLA",100)
