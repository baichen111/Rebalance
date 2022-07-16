import alpaca_trade_api as tradeapi
import requests
import json


class Rebalance:
    def __init__(self,perc_cash = 0.1,tickers = "NVDA,U,DDOG,TSLA,WMT",url = "https://paper-api.alpaca.markets"):
        self.perc_cash = perc_cash         # cash weight
        self.tickers = tickers
        self.perc_weight = (1 - self.perc_cash) / len(self.tickers.split(","))  # each stock percent weight to be allocated; each stock has same weight
        
        self.headers = json.loads(open("IDKEY.json", "r").read())
        self.api = tradeapi.REST(
            self.headers["APCA-API-KEY-ID"],
            self.headers["APCA-API-SECRET-KEY"],
            base_url = url,
        )
        
        self.current_pos = {}
        self.target_pos = {}
        self.total_equity = float(self.api.get_account().equity)   # total equity including cash
        
        self.sell_tick = {}
        self.buy_tick = {}
        
        #delete all pending orders before rebalance
        ord_cncl_url = url + "/v2/orders"
        requests.delete(ord_cncl_url, headers=self.headers)
        
     #retrieve current qty for each ticker in the pos_list , then add to current_pos dict
    def get_current_pos(self):
        pos_list = self.api.list_positions()
        for i in range(len(pos_list)):
            self.current_pos[pos_list[i].symbol] = int(pos_list[i].qty)
        return self.current_pos
    
    def last_trade_multi(self,symbols):  # get last trade price for each symbol and save them in a dict
        endpoint = "https://data.alpaca.markets/v2"
        "Extract last traded price and volume for multiple symbols"
        ltp = {}
        last_trade_url = endpoint + "/stocks/trades/latest"
        params = {"symbols": symbols}
        r = requests.get(last_trade_url, headers=self.headers, params=params)
        for symbol in symbols.split(","):
            ltp[symbol] = r.json()["trades"][symbol]["p"]
        return ltp
    
    #compute target qty for each ticker and add to target_pos dict
    def get_target_pos(self):
        ltp = self.last_trade_multi(self.tickers)
        for ticker in self.tickers.split(','):
            self.target_pos[ticker] = int(self.perc_weight*self.total_equity/ltp[ticker])
        return self.target_pos
    
    # sell and buy logic     
    def buy_sell(self):
        for k in self.target_pos.keys():   
            if not k in self.current_pos:
                self.buy_tick[k] = self.target_pos[k]
            elif self.target_pos[k] > self.current_pos[k]:
                self.buy_tick[k] = self.target_pos[k] - self.current_pos[k]
            elif  self.target_pos[k] < self.current_pos[k]:
                self.sell_tick[k] = self.current_pos[k] - self.target_pos[k]
            else:
                continue
        for k in self.current_pos.keys(): # if current pos ticker is not in target_pos, then sell all for that ticker
            if not k in self.target_pos:
                self.sell_tick[k] = self.current_pos[k]
        return [self.sell_tick,self.buy_tick]
    
    #control order placement
    def submit_orders(self):
        #submit order accouding to sell_tick and buy_tick
        for k,v in self.sell_tick.items():
            self.api.submit_order(k,v,"sell","market",time_in_force="day")
        for k,v in self.buy_tick.items():
            self.api.submit_order(k,v,"buy","market",time_in_force="day")
            
if __name__ == '__main__':
    myTrade = Rebalance(tickers="NVDA,SPYD,MSFT,TSLA")
    myTrade.get_current_pos()
    myTrade.get_target_pos()
    s,b = myTrade.buy_sell()
    print("sell: ",s)
    print("buy: ",b)
    myTrade.submit_orders()

    
