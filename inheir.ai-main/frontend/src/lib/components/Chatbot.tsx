import {
  Button,
  Textarea,
  type TextareaOnChangeData,
} from "@fluentui/react-components";
import { ArrowUpRegular } from "@fluentui/react-icons";
import {
  type ChangeEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type {
  Chat,
  ChatHistoryResponse,
  ChatResponse,
} from "@/lib/validators/types";

export const ChatUI = ({ caseId }: { caseId: string }) => {
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [query, setQuery] = useState<string>("");
  const [chatHistory, setChatHistory] = useState<Chat[]>([
    {
      content: "Welcome to the AI Chatbot! How can I assist you today?",
      type: "response",
    },
  ]);
  const [isFetching, setIsFetching] = useState<boolean>(false);
  const requests = useRef<AbortController | null>(null);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    const userChat: Chat = {
      content: query,
      type: "query",
    };
    setChatHistory((prev) => [...prev, userChat]);
    setIsFetching(true);

    const form = new FormData();
    form.append("case_id", caseId);
    form.append("query", userChat.content);

    const signal = requests.current?.signal;
    try {
      const res: Response = await fetch("/api/v1/chatbot/chat", {
        method: "POST",
        headers: {
          Accept: "application/json",
        },
        body: form,
        credentials: "include",
        signal,
      });

      if (res.ok) {
        await res.json().then((chatResponse: ChatResponse) => {
          if (signal?.aborted) return;
          const responseChat: Chat = {
            content: chatResponse.response.content,
            type: "response",
          };
          setChatHistory((prev) => [...prev, responseChat]);
        });
        await fetchChatHistory(signal);
      } else {
        const errorChat: Chat = {
          content:
            "Sorry, I couldn't process your request. Please try again later.",
          type: "response",
        };
        if (!signal?.aborted) setChatHistory((prev) => [...prev, errorChat]);
      }
    } catch {
      if (!signal?.aborted)
        setChatHistory((prev) => [
          ...prev,
          {
            content: "The connection failed. Please try again.",
            type: "response",
          },
        ]);
    } finally {
      if (!signal?.aborted) setIsFetching(false);
    }
  };

  const fetchChatHistory = useCallback(
    async (signal?: AbortSignal) => {
      setIsLoading(true);
      try {
        const res: Response = await fetch(`/api/v1/case/${caseId}/chats`, {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "include",
          signal,
        });
        if (res.ok) {
          const apiData = await res.json();
          if (signal?.aborted) return;
          const data: ChatHistoryResponse = apiData.chats;
          const newChatHistory: Chat[] = [];
          if (data) {
            data.chats.forEach((chat: ChatResponse) => {
              const queryChat: Chat = {
                content: chat.query.content,
                type: "query",
              };
              const responseChat: Chat = {
                content: chat.response.content,
                type: "response",
              };
              newChatHistory.push(queryChat, responseChat);
            });
          }
          setChatHistory((previous) =>
            newChatHistory.length > 0 ? newChatHistory : previous,
          );
        } else {
          setChatHistory([
            {
              content: "Failed to fetch chat history.",
              type: "response",
            },
          ]);
        }
      } catch (error) {
        if (signal?.aborted) return;
        console.error("Failed to fetch chat history:", error);
        setChatHistory([
          {
            content: "Failed to fetch chat history.",
            type: "response",
          },
        ]);
      } finally {
        if (!signal?.aborted) setIsLoading(false);
      }
    },
    [caseId],
  );

  useEffect(() => {
    const controller = new AbortController();
    requests.current = controller;
    setQuery("");
    setIsFetching(false);
    setChatHistory([
      {
        content: "Welcome to the AI Chatbot! How can I assist you today?",
        type: "response",
      },
    ]);
    fetchChatHistory(controller.signal);
    return () => controller.abort();
  }, [fetchChatHistory]);

  const renderChatBubble = (chat: Chat, index: number) => {
    const isUser = chat.type === "query";

    return (
      <div
        key={index}
        className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}
      >
        <div
          className={`max-w-[70%] rounded-lg px-4 py-2 ${
            isUser
              ? "bg-blue-500 text-white rounded-br-none whitespace-pre-wrap"
              : "bg-gray-200 text-gray-800 rounded-bl-none whitespace-pre-wrap"
          }`}
        >
          <Markdown remarkPlugins={[remarkGfm]}>{chat.content}</Markdown>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col w-full h-full">
      <div
        id="chat-container"
        className="p-4 flex flex-col shrink-0 overflow-y-auto scroll-smooth h-full max-h-[calc(90vh-70px)]"
        ref={(el) => {
          if (el && chatHistory.length > 0) el.scrollTop = el.scrollHeight;
        }}
      >
        {isLoading ? (
          <div className="flex justify-center items-center">
            <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
          </div>
        ) : (
          <>
            {chatHistory.length === 0 ? (
              <div className="text-center text-gray-500 mt-10">
                <p>No messages yet. Start a conversation!</p>
              </div>
            ) : (
              chatHistory.map((chat, index) => renderChatBubble(chat, index))
            )}
            {isFetching && (
              <div className="flex justify-start mb-4">
                <div className="bg-gray-200 text-gray-800 rounded-lg px-4 py-2 rounded-bl-none">
                  <div className="flex space-x-1">
                    <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"></div>
                    <div
                      className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"
                      style={{ animationDelay: "0.2s" }}
                    ></div>
                    <div
                      className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"
                      style={{ animationDelay: "0.4s" }}
                    ></div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
      <div className="bg-gray-100 border-t-2 flex-1">
        <form
          className="flex items-center p-3 gap-3 h-full"
          onSubmit={handleSubmit}
        >
          <Textarea
            placeholder="Type your message..."
            resize="vertical"
            size="medium"
            className="flex-1"
            onChange={(
              _: ChangeEvent<HTMLTextAreaElement>,
              data: TextareaOnChangeData,
            ) => {
              setQuery(data.value);
            }}
          />
          <Button
            appearance="primary"
            type="submit"
            shape="circular"
            disabled={isFetching}
          >
            <span>Send</span>
            <ArrowUpRegular />
          </Button>
        </form>
      </div>
    </div>
  );
};
