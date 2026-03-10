import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from mpl_finance import candlestick_ohlc
#import mpl_finance as mpf
import mplfinance as mpf 
import matplotlib.dates as mdates

def greet():
    print("Hello, welcome to learn Python with Lianghua!")


def testKdj():
    file_name = "demo.csv"
    df = pd.read_csv(file_name)
    
    # 重命名列（与之前一致）
    df.columns = ['stock_id', 'date', 'end_price', 'open_price', 'high_price', 'low_price', 'volumn']
    
    # 将日期字符串转换为 datetime 并设为索引（mplfinance 要求）
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df = calKdj(df)
    print(df[['kdj_k','kdj_d','kdj_j']])

    plt.figure()
    df['kdj_k'].plot(color = 'red',label='K')
    df['kdj_d'].plot(color = 'blue',label='D')
    df['kdj_j'].plot(color = 'green',label='J')
    plt.legend(loc = 'best')
    plt.xticks(rotation=30)
    plt.setp(plt.gca().get_xticklabels(), visible=True,rotation = 30)
    plt.grid(linestyle='-.')
    plt.title('KDJ')
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False
    plt.tight_layout()
    plt.show()


    return



def testMacd():
    file_name = "demo.csv"
    df = pd.read_csv(file_name)
    
    # 重命名列（与之前一致）
    df.columns = ['stock_id', 'date', 'end_price', 'open_price', 'high_price', 'low_price', 'volumn']
    
    # 将日期字符串转换为 datetime 并设为索引（mplfinance 要求）
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)

    df = cal_macd(df)
    print(df[['dif','dea','bar']])

    plt.figure()
    df['dea'].plot(color = 'red',label='DEA')
    df['dif'].plot(color = 'blue',label='DIF')
    plt.legend(loc = 'best')
    
    pos_bar = df[df['bar'] >= 0]['bar']
    neg_bar = df[df['bar'] < 0]['bar']
    plt.bar(pos_bar.index, pos_bar, color='red', width=0.8)
    plt.bar(neg_bar.index, neg_bar, color='green', width=0.8)

    

    plt.xticks(rotation=30)
    #这一步的作用是什么？     
    plt.setp(plt.gca().get_xticklabels(), visible=True,rotation = 30)
    #解释上一步的作用 
    plt.grid(linestyle='-.')
    plt.title('MACD')
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False
    plt.tight_layout()
    plt.show()




def testPandas_mplfinance():
    file_name = "demo.csv"
    df = pd.read_csv(file_name)
    
    # 重命名列（与之前一致）
    df.columns = ['stock_id', 'date', 'end_price', 'open_price', 'high_price', 'low_price', 'volumn']
    
    # 将日期字符串转换为 datetime 并设为索引（mplfinance 要求）
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    
    # 添加年月日信息（可选）
    df['year'] = df.index.year
    df['month'] = df.index.month
    df['day'] = df.index.day
    
    # 打印统计信息（保留你的原有统计）
    print(f"close min : {df['end_price'].min()}, close max : {df['end_price'].max()}, close mean : {df['end_price'].mean():.2f}")
    print(f"month close mean : {df.groupby('month')['end_price'].mean()}")
    print(f"month open mean : {df.groupby('month')['open_price'].mean()}")
    
    # 计算涨跌幅（保留）
    df['rise'] = df['end_price'].diff()
    df['rise_ratio'] = df['end_price'].pct_change()
    df['rise_rate'] = df['rise'] / df.shift(-1)['end_price']
    
    # mplfinance 要求列名必须为 Open, High, Low, Close, Volume（大小写敏感）
    df.rename(columns={
        'open_price': 'Open',
        'high_price': 'High',
        'low_price': 'Low',
        'end_price': 'Close',
        'volumn': 'Volume'
    }, inplace=True)
    

    my_color = mpf.make_marketcolors(
    up='r',           # 阳线红色（涨）
    down='g',         # 阴线绿色（跌）
    edge='i',         # 边框颜色继承自 up/down
    wick='i',         # 影线颜色继承
    volume={'up': 'red', 'down': 'green'},  # 成交量条颜色
    ohlc='i'          # OHLC 标记颜色继承（用于线型图）
)

    my_style = mpf.make_mpf_style(
    marketcolors=my_color,
    gridaxis='both',   # 双轴网格
    gridstyle='-.',    # 点划线
    rc={'font.family': 'ST Song'}  # 设置中文字体（需确保系统中有该字体）
)

    # 绘制 K 线图（带成交量）
    # 可选样式：'charles', 'binance', 'yahoo', 'blueskies' 等
    mpf.plot(df, type='candle', style=my_style, volume=True, figsize=(12,6),
             title='Stock K-line', ylabel='Price', ylabel_lower='Volume', mav=(5,10))
    

def testPandas_corrected():
    file_name = "demo.csv"
    df = pd.read_csv(file_name)
    
    # 重命名列
    df.columns = ['stock_id', 'date', 'end_price', 'open_price', 'high_price', 'low_price', 'volumn']
    
    # 将日期字符串转换为 datetime 类型
    df['date'] = pd.to_datetime(df['date'])
    
    # 转换为 Matplotlib 可用的数值日期（从公元1年1月1日起的天数）
    df['date_num'] = mdates.date2num(df['date'])

    df.set_index('date')
    
    # 添加年月日信息（可选）
    df['year'] = df['date'].dt.year
    df['month'] = df['date'].dt.month
    df['day'] = df['date'].dt.day
    
    # 打印一些统计信息
    print(f"close min : {df['end_price'].min()}, close max : {df['end_price'].max()}, close mean : {df['end_price'].mean()}")
    print(f"month close mean : {df.groupby('month')['end_price'].mean()}")
    print(f"month open mean : {df.groupby('month')['open_price'].mean()}")
    
    # 计算涨跌
    df['rise'] = df['end_price'].diff()
    df['rise_ratio'] = df['end_price'].pct_change()
    df['rise_rate'] = df['rise'] / df.shift(-1)['end_price']

    print(df)
    
    # 准备 K 线数据：必须按 (时间, 开盘, 最高, 最低, 收盘) 顺序
    quotes = df[['date_num', 'open_price', 'high_price', 'low_price', 'end_price']].values
    
    # 创建图形和坐标轴
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # 绘制 K 线图
    candlestick_ohlc(ax, quotes, width=0.6, colorup='r', colordown='g', alpha=0.8)
    
    # 设置 x 轴为日期格式，并自动调整刻度
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))  # 
    plt.xticks(rotation=30)
    ax.grid(True)
    
    plt.tight_layout()
    #plt.show()

    my_color = mpf.make_marketcolors(up='r', down='g', edge='i', wick='i', volume={'up:red', 'down:green'},ohlc = 'i')
    my_style = mpf.make_mpf_style(marketcolors=my_color, gridaxis = 'both', gridstyle='-.',rc = {'font.family': 'ST Song'})
    mpf.plot(df, type='candle', style=my_style, title="K Line By Volume", ylabel="Price", 
             volume=True,show_nontrading=False,ylabel_lower="volume",datetime_format="%Y-%m-%d",xrotation=45,linecolor='#00ff00',tight_layout=True)





def testReadFile():
    file_name = "demo.csv"
    end_price,volumn = np.loadtxt(file_name, delimiter=",", usecols=(2,6), unpack=True)


    print("End Price:", end_price)
    print("Volumn:", volumn)
    print(f"Average end price: {np.mean(end_price)}, Average volumn: {np.mean(volumn)}")
    print(f"Weighted average end price: {np.average(end_price, weights=volumn)}")
    print(f"Median end price: {np.median(end_price)}, Median volumn: {np.median(volumn)}")
    print(f"variance of end price: {np.var(end_price)}, variance of volumn: {np.var(volumn)}")
    print(f"standard deviation of end price: {np.std(end_price)}, standard deviation of volumn: {np.std(volumn)}")

    #对数波动率
    log_return = np.diff(np.log(end_price))
    daily_volatility = np.std(log_return) / np.mean(log_return)
    annualized_volatility = daily_volatility * np.sqrt(250)
    monthly_volatility = daily_volatility * np.sqrt(12)
    print(f"Daily Volatility: {daily_volatility}, Annualized Volatility: {annualized_volatility}, Monthly Volatility: {monthly_volatility}")

    x = np.arange(5)
    y = np.arange(10)
    print(f"exp of x: {np.exp(x)}, exp of y: {np.exp(y)}")
    
    N = 5
    weights = np.ones(N) / N
    print(f"weights {weights}")
    sma = np.convolve(weights,end_price)[N-1:-N+1]

 #解释一下下面的代码是什么意思 
    t = np.arange(N-1,len(end_price))


    print(f"linespace of 0 to 1 with 5 points: {np.linspace(-1,0,5)}")

    new_weights = np.linspace(-1,0,5)
    new_weights /= np.sum(new_weights)

    ema = np.convolve(new_weights,end_price)[N-1:-N+1]


    print(f"sma {sma}")
    print(f"ema {ema}")
    #怎么一张图上同时画出ema和sma呢？还需要图例，图例可以画在线条旁边吗

    plt.plot(t,end_price[N-1:],label="End Price")
    plt.plot(t,ema,label="EMA")

   # plt.plot(sma,linewidth=5,label="SMA")
   # plt.plot(ema,linewidth=5,label="EMA")

    plt.legend()

    plt.show()

    
def cal_macd(df,fast=12,slow=26,signal=9):
    ewma12 = df['end_price'].ewm(span=fast, adjust=False).mean()
    ewma26 = df['end_price'].ewm(span=slow, adjust=False).mean()
    df['dif'] = ewma12 - ewma26
    df['dea'] = df['dif'].ewm(span=signal, adjust=False).mean()
    df['bar'] = (df['dif'] - df['dea']) * 2



    return df

def calKdj(df , n=9):
    low_min = df['low_price'].rolling(n,min_periods=n).min()
    low_min.fillna(value=df['low_price'].expanding().min(), inplace=True)
    high_max = df['high_price'].rolling(n,min_periods=n).max()
    high_max.fillna(value=df['high_price'].expanding().max(), inplace=True)


    rsv = (df['end_price'] - low_min) / (high_max - low_min) * 100
    df['kdj_k'] = rsv.ewm(com=2).mean()
    df['kdj_d'] = df['kdj_k'].ewm(com=2).mean()
    df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']
    return df



def testPtp():
    file_name = "demo.csv"
    highPrice, lowPrice = np.loadtxt(file_name, delimiter=",",  usecols=(4,5), unpack=True)
    print(f"max price: {max(highPrice)}, min price: {min(lowPrice)}")
    #print("max price:{}".format(max(highPrice)))
    print(f"max - min of high price : {np.ptp(highPrice)}, max - min of low price : {np.ptp(lowPrice)}")

if __name__ == "__main__":
    greet()
    #testReadFile()
    
    #testPtp()
    #testPandas_mplfinance()
    #testMacd()
    testKdj()
