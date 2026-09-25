// TestResponseParser.cpp : Defines the entry point for the console application.
//

#include "stdafx.h"
#include <boost/detail/lightweight_test.hpp>
#include <ResponseParser.h>
#include <string>
#include <sstream>
#include <boost/archive/text_woarchive.hpp>

void test_pipe_channel();

void test_1() {
  WCHAR resp[] = L"action=noop\n.\n";
  DWORD len = wcslen(resp);
  std::wstring commit;
  weasel::Context ctx;
  weasel::Status status;
  weasel::ResponseParser parser(&commit, &ctx, &status);
  BOOST_TEST(parser(resp, len));
  BOOST_TEST(commit.empty());
  BOOST_TEST(ctx.empty());
}

void test_2() {
  WCHAR resp[] =
      L"action=commit\n"
      L"commit=教這句話上屏=3.14\n.\n";
  DWORD len = wcslen(resp);
  std::wstring commit;
  weasel::Context ctx;
  weasel::Status status;
  ctx.aux.str = L"從前的值";
  weasel::ResponseParser parser(&commit, &ctx, &status);
  BOOST_TEST(parser(resp, len));
  BOOST_TEST(commit == L"教這句話上屏=3.14");
  BOOST_TEST(ctx.preedit.empty());
  BOOST_TEST(ctx.aux.str == L"從前的值");
  BOOST_TEST(ctx.cinfo.candies.empty());
}

void test_3() {
  WCHAR resp[] =
      L"action=ctx\n"
      L"ctx.preedit=寫作串=3.14\n"
      L"ctx.aux=sie'zuoh'chuan=3.14\n.\n";
  DWORD len = wcslen(resp);
  std::wstring commit;
  weasel::Context ctx;
  weasel::Status status;
  weasel::ResponseParser parser(&commit, &ctx, &status);
  BOOST_TEST(parser(resp, len));
  BOOST_TEST(commit.empty());
  BOOST_TEST(ctx.preedit.str == L"寫作串=3.14");
  BOOST_TEST(ctx.preedit.attributes.empty());
  BOOST_TEST(ctx.aux.str == L"sie'zuoh'chuan=3.14");
}

void test_4() {
  WCHAR resp[] =
      L"action=commit,ctx\n"
      L"ctx.preedit=候選乙=3.14\n"
      L"ctx.preedit.cursor=0,3\n.\n";
  DWORD len = wcslen(resp);
  std::wstring commit;
  weasel::Context ctx;
  weasel::Status status;
  weasel::ResponseParser parser(&commit, &ctx, &status);
  BOOST_TEST(parser(resp, len));
  BOOST_TEST(commit.empty());
  BOOST_TEST(ctx.preedit.str == L"候選乙=3.14");
  BOOST_TEST_EQ(1u, ctx.preedit.attributes.size());
  if (ctx.preedit.attributes.empty())
    return;
  weasel::TextAttribute attr0 = ctx.preedit.attributes[0];
  BOOST_TEST_EQ(weasel::HIGHLIGHTED, attr0.type);
  BOOST_TEST_EQ(0, attr0.range.start);
  BOOST_TEST_EQ(3, attr0.range.end);
  BOOST_TEST_EQ(-1, attr0.range.cursor);
  BOOST_TEST(ctx.aux.empty());
}

void test_cursor_fields() {
  weasel::Context ctx;
  weasel::ResponseParser parser(nullptr, &ctx);
  parser.Feed(L"action=ctx");
  parser.Feed(L"ctx.preedit=abc");
  parser.Feed(L"ctx.preedit.cursor=0");
  BOOST_TEST(ctx.preedit.attributes.empty());
  parser.Feed(L"ctx.preedit.cursor=");
  BOOST_TEST(ctx.preedit.attributes.empty());
  parser.Feed(L"ctx.preedit.cursor=0,3,2");
  BOOST_TEST_EQ(1u, ctx.preedit.attributes.size());
  if (!ctx.preedit.attributes.empty())
    BOOST_TEST_EQ(2, ctx.preedit.attributes[0].range.cursor);
}

void test_candidates() {
  weasel::CandidateInfo expected;
  expected.candies = {weasel::Text(L"\u5019\u9078\u7532"),
                      weasel::Text(L"\u5019\u9078\u4e59")};
  expected.labels = {weasel::Text(L"1"), weasel::Text(L"2")};
  expected.comments = {weasel::Text(L"first"), weasel::Text(L"second")};
  expected.highlighted = 1;
  expected.totalPages = 1;
  expected.is_last_page = true;
  std::wstringstream ss;
  boost::archive::text_woarchive archive(ss);
  archive << expected;
  std::wstring response = L"action=ctx\nctx.cand=" + ss.str() + L"\n.\n";
  weasel::Context ctx;
  weasel::ResponseParser parser(nullptr, &ctx);
  BOOST_TEST(parser(response.data(), static_cast<UINT>(response.size())));
  BOOST_TEST(ctx.cinfo == expected);
}

void test_incomplete_response() {
  WCHAR response[] = L"action=noop\n";
  weasel::ResponseParser parser(nullptr);
  BOOST_TEST(!parser(response, static_cast<UINT>(wcslen(response))));
}

int _tmain(int argc, _TCHAR* argv[]) {
  test_1();
  test_2();
  test_3();
  test_4();
  test_cursor_fields();
  test_candidates();
  test_incomplete_response();
  test_pipe_channel();
  return boost::report_errors();
}
