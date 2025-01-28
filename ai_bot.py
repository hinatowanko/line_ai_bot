import os
import sys

from flask import Flask, request, abort

from linebot.v3 import WebhookHandler

from linebot.v3.webhooks import MessageEvent, TextMessageContent, UserSource
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, TextMessage, ReplyMessageRequest
from linebot.v3.exceptions import InvalidSignatureError

from openai import AzureOpenAI
# get LINE credentials from environment variables
channel_access_token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
channel_secret = os.environ["LINE_CHANNEL_SECRET"]

if channel_access_token is None or channel_secret is None:
    print("Specify LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET as environment variable.")
    sys.exit(1)

# get Azure OpenAI credentials from environment variables
azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
azure_openai_api_version = os.getenv("AZURE_OPENAI_API_VERSION")
azure_openai_model = os.getenv("AZURE_OPENAI_MODEL")

if azure_openai_endpoint is None or azure_openai_api_key is None or azure_openai_api_version is None:
    raise Exception(
        "Please set the environment variables AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and AZURE_OPENAI_API_VERSION."
    )


handler = WebhookHandler(channel_secret)
configuration = Configuration(access_token=channel_access_token)

app = Flask(__name__)
ai = AzureOpenAI(
    azure_endpoint=azure_openai_endpoint, api_key=azure_openai_api_key, api_version=azure_openai_api_version
)


# LINEボットからのリクエストを受け取るエンドポイント
@app.route("/callback", methods=["POST"])
def callback():
    # get X-Line-Signature header value
    signature = request.headers["X-Line-Signature"]

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError as e:
        abort(400, e)

    return "OK"


chat_history = []


# チャット履歴を初期化する関数
def init_chat_history():
    chat_history.clear()
    system_role = {
        "role": "system",
        "content": [
            {
                "type": "text",
                "text": "あなたはアーチェリー部の部員です。新入部員を募集しています。優しく丁寧に敬語を使って話します。",
            },
        ],
    }
    chat_history.append(system_role)


"""
def get_ai_response(from_user, text):
    res = []
    res.append(TextMessage(text=f"{from_user}！！！"))
    if "体験会" in text:
        res.append(TextMessage(text="こちらのホームページを見てください。https://kobe-archery.main.jp" ))
    return res
"""

# AIからの応答を取得する関数
def get_ai_response(from_user, text):
    # 「留学生」が含まれる場合、system_role を変更
    if "留学生" in text or "りゅうがくせい" in text:
        # system_role を変更
        chat_history[0] = {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": "あなたはアーチェリー部の部員です。新入部員を募集しています。ひらがなのみを使って話します。漢字をつかってはいけません。",
                },
            ],
        }

        # 変更後の chat_history を確認
        print("Updated system_role: ", chat_history[0])

    # ユーザーのメッセージを記録
    user_msg = {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": text,
            },
        ],
    }
    chat_history.append(user_msg)

    # AIのパラメータ
    parameters = {
        "model": azure_openai_model,
        "max_tokens": 100,
        "temperature": 0.5,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "stop": ["\n"],
        "stream": False,
    }

    # AIから返信を取得
    try:
        ai_response = ai.chat.completions.create(messages=chat_history, **parameters)
        res_text = ai_response.choices[0].message.content

        # ひらがなモードなら変換
        print("AI Response before conversion:", res_text)  # デバッグ用

    except Exception as e:
        print("Error during AI response:", e)
        res_text = "申し訳ありません。エラーが発生しました。"

    # AIの返信を記録
    ai_msg = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": res_text},
        ],
    }
    chat_history.append(ai_msg)
    return res_text





# 　返信メッセージを生成する関数
def generate_response(from_user, text):
    res = []
    print(type(text), text)
    if text in ["リセット", "初期化", "クリア", "reset", "clear"]:
        # チャット履歴を初期化
        init_chat_history()
        res = [TextMessage(text="チャットをリセットしました。")]
    elif "体験会" in text:
        res = [TextMessage(text="こちらのホームページを見てください。https://kobe-archery.main.jp")]
    else:
        # AIを使って返信を生成
        res = [TextMessage(text=get_ai_response(from_user, text))]
    return res



# メッセージを受け取った時の処理
@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    # 送られてきたメッセージを取得
    text = event.message.text

    # 返信メッセージの送信
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        res = []
        if isinstance(event.source, UserSource):
            # ユーザー情報が取得できた場合
            profile = line_bot_api.get_profile(event.source.user_id)
            # 返信メッセージを生成
            res = generate_response(profile.display_name, text)
        else:
            # ユーザー情報が取得できなかった場合
            # fmt: off
            # 定型文の返信メッセージ
            res = [
                TextMessage(text="ユーザー情報を取得できませんでした。"),
                TextMessage(text=f"メッセージ：{text}")
            ]
            # fmt: on

        # メッセージを送信
        line_bot_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=res))





if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Render環境に合わせてポートを取得
    app.run(host="0.0.0.0", port=port, debug=True)
