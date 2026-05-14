import datetime, discord, json, os, re

# 현재 시각을 한국어 형식으로 반환
def Current_Time() -> str:
    return datetime.datetime.now().strftime('%Y년 %m월 %d일 %H:%M:%S')

# 오류 다이얼로그 Embed 반환
def Error_Dialog_Embed(message: str) -> discord.Embed:
    return discord.Embed(description=f"⚠️ {message}", color=discord.Color.red())

# 성공 다이얼로그 Embed 반환
def Success_Dialog_Embed(message: str) -> discord.Embed:
    return discord.Embed(description=f"✅ {message}", color=discord.Color.green())

# 로그 출력 스크립트
def Print_Log(Cog_Name: str, Action: str, Guild_Name: str, Author_Name: str, Target_Name: str = None, Extra: str = None) -> None:
    Log_Text = f"[{Cog_Name}] {Action} (서버: {Guild_Name}, 요청자: {Author_Name}"
    if Target_Name:
        Log_Text += f", 대상: {Target_Name}"
    if Extra:
        Log_Text += f", {Extra}"
    Log_Text += ")"
    print(Log_Text)

# 데이터 저장 스크립트
def Save_Data(Path: str, Data: dict) -> None:
    Dir_Name = os.path.dirname(Path)
    if Dir_Name and not os.path.exists(Dir_Name):
        os.makedirs(Dir_Name, exist_ok=True)
    with open(Path, 'w', encoding='utf-8') as file:
        json.dump(Data, file, ensure_ascii=False, indent=4)

# 데이터 불러오기 스크립트
def Load_Data(Path: str) -> dict:
    if not os.path.exists(Path):
        return {}
    try:
        with open(Path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except:
        return {}

# 기간 파싱 스크립트 (초, 분, 시간, 일, 주, 개월, 년 처리 가능)
def Parse_Duration(Duration: str):
    Match = re.match(r"(\d+)(초|분|시간|일|주|개월|년)", Duration)
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
        Total_Seconds = Value * 2592000
    elif Unit == "년":
        Total_Seconds = Value * 31536000
    else:
        return None

    return datetime.timedelta(seconds=Total_Seconds)

# 공용 확인 뷰 클래스
async def Button_Interaction(self, interaction, Value):
    if interaction.user != self.Author:
        return await interaction.response.send_message("버튼을 조작할 권한이 없습니다.", ephemeral=True)
    
    self.Value = Value

    await interaction.response.defer()
    self.stop()