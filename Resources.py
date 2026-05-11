import datetime, discord, json, os, re

# 현재 시각을 한국어 형식으로 반환
def Current_Time() -> str:
    return datetime.datetime.now().strftime('%Y년 %m월 %d일 %H:%M:%S')

# 오류 다이얼로그 Embed
def Error_Dialog_Embed(message: str) -> discord.Embed:
    return discord.Embed(description=f"⚠️ {message}", color=discord.Color.red())

# 성공 다이얼로그 Embed
def Success_Dialog_Embed(message: str) -> discord.Embed:
    return discord.Embed(description=f"✅ {message}", color=discord.Color.green())

# 로그 출력
def Print_Log(cog: str, action: str, guild: str, author: str, target: str = None, extra: str = None) -> None:
    Log_Text = f"[{cog}] {action} (서버: {guild}, 요청자: {author}"
    if target:
        Log_Text += f", 대상: {target}"
    if extra:
        Log_Text += f", {extra}"
    Log_Text += ")"
    print(Log_Text)

# 데이터 저장
def Save_Data(path: str, data: dict) -> None:
    Dir_Name = os.path.dirname(path)
    if Dir_Name and not os.path.exists(Dir_Name):
        os.makedirs(Dir_Name, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

# 데이터 불러오기
def Load_Data(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except:
        return {}

# 기간 파싱 (ex: 10초, 3분, 1시간, 1일, 1주, 1개월, 1년)
def Parse_Duration(duration: str):
    Match = re.match(r"(\d+)(초|분|시간|일|주|개월|년)", duration)
    if not Match:
        return None
    
    Value, Unit = Match.groups()
    Value = int(Value)
    
    if Unit == "초":
        Total_Seconds = Value
    elif Unit == "분":
        Total_Seconds = Value * 60
    elif Unit == "시간":
        Total_Seconds = Value * 3600
    elif Unit == "일":
        Total_Seconds = Value * 86400
    elif Unit == "주":
        Total_Seconds = Value * 604800
    elif Unit == "개월":
        Total_Seconds = Value * 2592000 # 30일 기준
    elif Unit == "년":
        Total_Seconds = Value * 31536000 # 365일 기준
    else:
        return None

    return datetime.timedelta(seconds=Total_Seconds)