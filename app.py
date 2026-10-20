from io import BytesIO

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Bags & Luggage AI SDR", layout="wide")


@st.cache_data
def load_data():
    qualified = pd.read_csv("data/qualified_leads.csv")
    excluded = pd.read_csv("data/excluded_leads.csv")
    return qualified, excluded


def to_excel(df):
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    return buffer.getvalue()


qualified, excluded = load_data()

st.title("Bags & Luggage AI SDR")
st.caption("Indian businesses likely to buy bags and luggage, scored 0-100 from evidence on their websites.")

counts = qualified["intent_label"].value_counts()
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Discovered", len(qualified) + len(excluded))
col2.metric("Qualified", len(qualified))
col3.metric("High intent", counts.get("High", 0))
col4.metric("Medium intent", counts.get("Medium", 0))
col5.metric("Low intent", counts.get("Low", 0))

st.sidebar.header("Filters")
labels = st.sidebar.multiselect("Intent", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
categories = sorted(qualified["business_type"].dropna().unique())
chosen_categories = st.sidebar.multiselect("Business category", categories, default=categories)
min_score = st.sidebar.slider("Minimum score", 0, 100, 0)
search = st.sidebar.text_input("Search company")

filtered = qualified[
    qualified["intent_label"].isin(labels)
    & qualified["business_type"].isin(chosen_categories)
    & (qualified["score"] >= min_score)
]
if search:
    filtered = filtered[filtered["company_name"].str.contains(search, case=False, na=False)]
filtered = filtered.sort_values("score", ascending=False)

tab_leads, tab_excluded = st.tabs([f"Qualified leads ({len(filtered)})", f"Excluded ({len(excluded)})"])

with tab_leads:
    st.dataframe(
        filtered[["company_name", "score", "intent_label", "business_type", "emails", "phones",
                  "location", "intent_evidence", "missing_data", "source_url"]],
        column_config={
            "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
            "source_url": st.column_config.LinkColumn("Source"),
        },
        hide_index=True,
        width="stretch",
    )

    download1, download2 = st.columns(2)
    download1.download_button("Download CSV", filtered.to_csv(index=False), "qualified_leads.csv", "text/csv")
    download2.download_button("Download Excel", to_excel(filtered), "qualified_leads.xlsx")

    st.subheader("Lead details")
    if filtered.empty:
        st.info("No leads match the filters.")
    else:
        name = st.selectbox("Choose a lead", filtered["company_name"])
        lead = filtered[filtered["company_name"] == name].iloc[0]

        st.markdown(f"### {lead['company_name']} — {lead['score']}/100 ({lead['intent_label']} intent)")
        f1, f2, f3, f4, f5 = st.columns(5)
        f1.metric("Fit", f"{lead['fit_score']}/25")
        f2.metric("Intent", f"{lead['intent_score']}/30")
        f3.metric("Scale", f"{lead['scale_score']}/15")
        f4.metric("Recency", f"{lead['recency_score']}/15")
        f5.metric("Contact", f"{lead['contact_score']}/15")

        left, right = st.columns(2)
        with left:
            st.markdown("**Contact**")
            st.write(f"Email: {lead['emails'] if pd.notna(lead['emails']) else '—'}")
            st.write(f"Phone: {lead['phones'] if pd.notna(lead['phones']) else '—'}")
            st.write(f"Contact person: {lead['contact_person'] if pd.notna(lead['contact_person']) else '—'}")
            st.write(f"Location: {lead['location'] if pd.notna(lead['location']) else '—'}")
            st.write(f"Website: {lead['source_url']}")
            if pd.notna(lead["contact_page_url"]):
                st.write(f"Contact page: {lead['contact_page_url']}")
            st.write(f"Collected on: {lead['collected_on']}")
        with right:
            st.markdown("**Evidence**")
            st.write(f"Buying signals: {lead['intent_evidence']}")
            if pd.notna(lead["intent_quote"]):
                st.write(f"Quote from site: \"{lead['intent_quote']}\"")
            st.write(f"Missing data: {lead['missing_data']}")
            st.markdown("**Likely bag requirement** *(AI assumption, not verified)*")
            st.write(lead["likely_bag_need"] if pd.notna(lead["likely_bag_need"]) else "—")

        st.markdown("**Score explanation**")
        st.write(lead["explanation"])

with tab_excluded:
    st.write("Leads that did not qualify, with the reason.")
    st.dataframe(
        excluded[["domain", "company_name", "exclusion_reason", "lead_type", "emails", "phones", "source_url"]],
        column_config={"source_url": st.column_config.LinkColumn("Source")},
        hide_index=True,
        width="stretch",
    )
    st.download_button("Download excluded CSV", excluded.to_csv(index=False), "excluded_leads.csv", "text/csv")
