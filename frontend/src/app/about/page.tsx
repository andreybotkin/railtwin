import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowLeft, Clock3, MapPinned, Route, TrainFront } from 'lucide-react';
import { getLocale } from 'next-intl/server';

import { Button } from '@/components/ui';
import { pageMetadata } from '@/lib/seo';

export const metadata: Metadata = pageMetadata({
  title: 'Thailand Railway Map, Train Tracker & SRT Timetable Guide',
  description:
    'Use RailTwin to explore Thailand railway routes, stations, SRT timetable data and estimated train movement on one interactive map.',
  path: '/about',
  keywords: [
    'Thailand railway routes',
    'Thailand train stations map',
    'Bangkok train map',
    'SRT routes and stations',
  ],
});

const copy = {
  en: {
    back: 'Open the live map',
    eyebrow: 'Thailand railway guide',
    title: 'Thailand railway map and train tracker',
    intro:
      'RailTwin brings Thailand railway routes, stations, public timetable data and simulated train movement together on one interactive map. Use it to understand the national rail network and follow a train’s expected journey progress.',
    sections: [
      [
        'Explore Thailand’s railway network',
        'View the Northern, Northeastern, Eastern and Southern lines, zoom into station locations and select a route to understand how services connect Bangkok with destinations across Thailand.',
        MapPinned,
      ],
      [
        'Find trains and stations',
        'Search by train or station, inspect calling patterns and view the stop timeline for available services. The interface is available in English and Thai.',
        TrainFront,
      ],
      [
        'Check timetable context',
        'Published passenger schedules provide planned arrival and departure context. Always confirm important journeys, fares and service changes with the official State Railway of Thailand channels.',
        Clock3,
      ],
      [
        'Understand the movement display',
        'Train positions, progress and delay indicators can be estimated from timetable and movement data. They are designed for exploration and may not represent an official real-time operational position.',
        Route,
      ],
    ],
    faqTitle: 'Frequently asked questions',
    faq: [
      [
        'Is RailTwin an official SRT service?',
        'No. RailTwin is an independent open-source project and is not affiliated with or endorsed by the State Railway of Thailand.',
      ],
      [
        'Are the train positions live?',
        'The map visualizes the latest available movement and timetable context. Some positions and delay values are simulated or estimated, so they should not be used for time-critical travel decisions.',
      ],
      [
        'Which Thailand railway lines are shown?',
        'The map covers the main Northern, Northeastern, Eastern and Southern railway corridors and their available stations and services.',
      ],
    ],
  },
  th: {
    back: 'เปิดแผนที่รถไฟ',
    eyebrow: 'คู่มือรถไฟไทย',
    title: 'แผนที่รถไฟไทยและระบบติดตามรถไฟ',
    intro:
      'RailTwin รวมเส้นทางรถไฟ สถานี ข้อมูลตารางรถไฟสาธารณะ และการจำลองตำแหน่งรถไฟไว้ในแผนที่เดียว เพื่อช่วยสำรวจเครือข่ายรถไฟไทยและดูความคืบหน้าของการเดินทาง',
    sections: [
      [
        'สำรวจเครือข่ายรถไฟไทย',
        'ดูสายเหนือ สายตะวันออกเฉียงเหนือ สายตะวันออก และสายใต้ ซูมดูตำแหน่งสถานี และเลือกเส้นทางเพื่อดูการเชื่อมต่อจากกรุงเทพฯ ไปยังจุดหมายทั่วประเทศ',
        MapPinned,
      ],
      [
        'ค้นหาขบวนรถและสถานี',
        'ค้นหาขบวนรถหรือสถานี ดูลำดับจุดจอดและไทม์ไลน์ของบริการที่มีข้อมูล อินเทอร์เฟซรองรับภาษาไทยและอังกฤษ',
        TrainFront,
      ],
      [
        'ตรวจสอบข้อมูลตารางรถไฟ',
        'ตารางโดยสารสาธารณะใช้แสดงเวลาถึงและเวลาออกตามแผน โปรดยืนยันการเดินทาง ค่าโดยสาร และการเปลี่ยนแปลงบริการกับช่องทางทางการของการรถไฟแห่งประเทศไทย',
        Clock3,
      ],
      [
        'ทำความเข้าใจตำแหน่งบนแผนที่',
        'ตำแหน่ง ความคืบหน้า และค่าความล่าช้าบางส่วนอาจคำนวณจากตารางและข้อมูลการเคลื่อนที่ จึงไม่ใช่ตำแหน่งปฏิบัติการแบบเรียลไทม์อย่างเป็นทางการ',
        Route,
      ],
    ],
    faqTitle: 'คำถามที่พบบ่อย',
    faq: [
      [
        'RailTwin เป็นบริการทางการของ ร.ฟ.ท. หรือไม่',
        'ไม่ใช่ RailTwin เป็นโครงการโอเพนซอร์สอิสระและไม่ได้มีความเกี่ยวข้องหรือได้รับการรับรองจากการรถไฟแห่งประเทศไทย',
      ],
      [
        'ตำแหน่งรถไฟเป็นแบบเรียลไทม์หรือไม่',
        'แผนที่แสดงข้อมูลการเคลื่อนที่และตารางล่าสุดที่มี บางตำแหน่งและค่าความล่าช้าเป็นการจำลองหรือประมาณการ จึงไม่ควรใช้ตัดสินใจเดินทางที่ต้องอาศัยเวลาที่แม่นยำ',
      ],
      [
        'แผนที่แสดงเส้นทางใดบ้าง',
        'แผนที่ครอบคลุมเส้นทางหลักสายเหนือ สายตะวันออกเฉียงเหนือ สายตะวันออก และสายใต้ รวมถึงสถานีและขบวนรถที่มีข้อมูล',
      ],
    ],
  },
} as const;

export default async function AboutPage() {
  const locale = await getLocale();
  const content = copy[locale === 'th' ? 'th' : 'en'];
  const faqData = {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: content.faq.map(([question, answer]) => ({
      '@type': 'Question',
      name: question,
      acceptedAnswer: { '@type': 'Answer', text: answer },
    })),
  };

  return (
    <main
      className="min-h-dvh"
      style={{ background: 'var(--page-bg)', color: 'var(--panel-text)' }}
    >
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(faqData).replace(/</g, '\\u003c'),
        }}
      />
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 py-4 pb-10 sm:px-6 sm:py-6">
        <Button
          asChild
          variant="ghost"
          className="h-12 self-start rounded-2xl px-4"
        >
          <Link href="/">
            <ArrowLeft className="mr-2 h-4 w-4" />
            {content.back}
          </Link>
        </Button>
        <header
          className="rounded-[28px] border px-5 py-7 sm:px-8 sm:py-10"
          style={{
            background: 'var(--panel-bg)',
            borderColor: 'var(--panel-border)',
          }}
        >
          <p
            className="text-[11px] font-semibold tracking-[0.24em] uppercase"
            style={{ color: 'var(--panel-subtext)' }}
          >
            {content.eyebrow}
          </p>
          <h1 className="mt-3 max-w-3xl text-3xl font-semibold tracking-tight sm:text-5xl">
            {content.title}
          </h1>
          <p
            className="mt-5 max-w-3xl text-base leading-7 sm:text-lg"
            style={{ color: 'var(--panel-subtext)' }}
          >
            {content.intro}
          </p>
        </header>
        <section
          className="grid gap-3 sm:grid-cols-2"
          aria-label={content.title}
        >
          {content.sections.map(([title, body, Icon]) => (
            <article
              key={title}
              className="rounded-[24px] border px-5 py-5"
              style={{
                background: 'var(--panel-bg-strong)',
                borderColor: 'var(--panel-inner-ring)',
              }}
            >
              <Icon className="h-5 w-5" aria-hidden="true" />
              <h2 className="mt-4 text-lg font-semibold tracking-tight">
                {title}
              </h2>
              <p
                className="mt-2 text-sm leading-6"
                style={{ color: 'var(--panel-subtext)' }}
              >
                {body}
              </p>
            </article>
          ))}
        </section>
        <section
          className="rounded-[28px] border px-5 py-6 sm:px-8"
          style={{
            background: 'var(--panel-bg)',
            borderColor: 'var(--panel-border)',
          }}
        >
          <h2 className="text-2xl font-semibold tracking-tight">
            {content.faqTitle}
          </h2>
          <div className="mt-5 divide-y">
            {content.faq.map(([question, answer]) => (
              <article key={question} className="py-5 first:pt-0 last:pb-0">
                <h3 className="font-semibold">{question}</h3>
                <p
                  className="mt-2 text-sm leading-6"
                  style={{ color: 'var(--panel-subtext)' }}
                >
                  {answer}
                </p>
              </article>
            ))}
          </div>
        </section>
        <p
          className="text-center text-xs"
          style={{ color: 'var(--panel-subtext)' }}
        >
          <Link href="/open-data" className="underline underline-offset-4">
            Data sources and methodology
          </Link>
        </p>
      </div>
    </main>
  );
}
