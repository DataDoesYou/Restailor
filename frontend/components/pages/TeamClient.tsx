"use client";
import Image from "next/image";

export default function TeamClient() {
  return (
    <div className="mx-auto max-w-3xl space-y-12 pb-8 px-4 md:px-0 pt-6" role="main">
      <section>
        <h1 className="text-3xl font-bold mb-6">Meet our team</h1>
        <div className="text-slate-300 space-y-4 max-w-2xl leading-relaxed">
          <p>
            Restailor is a free, open-source AI tool for resume analysis, resume tailoring, and job application workflows. It is hosted for job seekers to use with their own provider keys.
          </p>
          <p>
            The project is founder-led and independently operated, with a direct focus on practical utility, responsible data handling, and keeping the hosted experience available as a community-friendly tool.
          </p>
        </div>
      </section>

      <section>
        <div className="flex flex-col md:flex-row gap-8 items-start">
          {/* Photo placeholder - user must place image at /public/team/gueorgui-tankov.jpg */}
          <div className="relative w-48 h-48 shrink-0 rounded-xl overflow-hidden bg-slate-800 border border-slate-700">
            <Image
              src="/team/gueorgui.jpg"
              alt="Gueorgui Tankov"
              fill
              className="object-cover"
              sizes="(max-width: 768px) 192px, 192px"
              priority
            />
          </div>

          <div className="space-y-4">
            <div>
              <h2 className="text-xl font-bold text-slate-100">Gueorgui Tankov</h2>
              <div className="text-lg font-medium text-slate-300">Founder and Lead AI Engineer</div>
              <div className="text-sm text-slate-400 mt-1">Former data leader at Incyte and Morgan Stanley</div>
            </div>

            <p className="text-slate-300 leading-relaxed text-sm">
              Gueorgui has 15 years of experience building production data platforms. As founder of DataDoesYou and Restailor, he owns the full technical lifecycle from architecture through deployment. He builds secure AI systems for resume analysis and job matching with strict PII protection, and maintains Restailor as an open-source project.
            </p>

            <div>
              <a 
                href="https://linkedin.com/in/gtankov/" 
                target="_blank" 
                rel="noopener noreferrer"
                className="inline-flex items-center text-amber-400 hover:text-amber-300 transition-colors text-sm font-medium gap-1"
              >
                Connect on LinkedIn <span>&rarr;</span>
              </a>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
