# app.py (v3 版修正版)

# =======================================================================================
#  1. 匯入必要的工具 (Import Libraries)
# =======================================================================================
import os
import re
from flask import Flask, request, abort

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from config import LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN
from rag import build_context
from summarize import summarize_with_gpt


# =======================================================================================
#  2. 初始化應用程式 (Initialize Application)
# =======================================================================================
app = Flask(__name__)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


# =======================================================================================
#  3. 輔助函式 (Helper Functions)
# =======================================================================================
def format_response(text: str) -> str:
    formatted_text = re.sub(r'\n(\d+\.)', r'\n\n\1', text)
    formatted_text = formatted_text.replace("###", "##")
    return formatted_text


# =======================================================================================
#  4. 主要路由與邏輯 (Main Routes & Logic)
# =======================================================================================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body}")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent):
    user_text = event.message.text.strip()
    user_id = event.source.user_id
    if not user_text:
        return

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        # --- ▼▼▼ 回覆的 LOG 在這裡 ▼▼▼ ---
        # 步驟 A: 執行 RAG 檢索
        print(f"LOG: 接收到查詢 '{user_text}', 開始建立上下文...\n")
        context = build_context(user_text)
        print(f"LOG: 上下文建立完成。")

        # 步驟 B: 呼叫 GPT 生成總結
        print("LOG: 開始呼叫 OpenAI API 進行總結...\n")
        raw_answer = summarize_with_gpt(user_text, context)
        print(f"LOG: 回應完成。")
        # --- ▲▲▲ 回覆的 LOG 在這裡 ▲▲▲ ---

        # 步驟 C: 美化排版
        answer = format_response(raw_answer)

        # 步驟 D: 使用 v3 reply 
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=answer)]
            )
        )


# =======================================================================================
#  5. 啟動應用程式 (Run Application)
# =======================================================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
