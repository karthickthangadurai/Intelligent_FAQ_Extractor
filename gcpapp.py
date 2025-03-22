import streamlit as st
import pandas as pd
import logging
import os
from dotenv import load_dotenv
import time
import base64
from commonscrape import *
import google.cloud.storage as storage

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("faq_extractor.log")
    ]
)
logger = logging.getLogger("faq_extractor")

def get_csv_download_link(df, filename="extracted_faqs.csv"):
    """
    Generate a download link for the CSV file.
    """
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">Download CSV file</a>'
    return href

def upload_to_gcp_bucket(file_path, bucket_name, destination_blob_name):
    """
    Upload a file to a GCP bucket
    """
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(file_path)
        return True, f"File {destination_blob_name} uploaded to {bucket_name}."
    except Exception as e:
        return False, f"Error uploading to GCP: {str(e)}"

def main():
    """
    Main Streamlit application.
    """
    st.set_page_config(
        page_title="FAQ Extractor",
        page_icon="📝",
        layout="wide"
    )
    
    # Initialize session state variables
    if 'progress_placeholder' not in st.session_state:
        st.session_state.progress_placeholder = st.empty()
    if 'status_placeholder' not in st.session_state:
        st.session_state.status_placeholder = st.empty()
    if 'results_df' not in st.session_state:
        st.session_state.results_df = None
    if 'missed_urls' not in st.session_state:
        st.session_state.missed_urls = []
    if 'extraction_complete' not in st.session_state:
        st.session_state.extraction_complete = False
    
    # Create side navigation bar
    with st.sidebar:
        st.sidebar.title("FAQ Extractor Tool")
        
        # API Keys Input
        st.header("API Keys")
        firecrawl_api_key = st.text_input("Firecrawl API Key", type="password", key="firecrawl_api")
        google_api_key = st.text_input("Google API Key", type="password", key="google_api")
        
        # Input section
        st.header("Input Options")
        input_option = st.radio("Choose input method:", ["Single URL", "CSV File Upload"], key="input_option")
        
        urls = None
        
        if input_option == "Single URL":
            url = st.text_input("Enter a URL:", "https://platts.my.site.com/CIKnowledgeBase/s/article/How-do-I-reset-my-password-for-S-P-Global-Commodity-Insights-website", key="url_input")
            if url:
                urls = url
        else:
            uploaded_file = st.file_uploader("Upload a CSV file with URLs (Column Name: 'Links' or 'URL'):", type=["csv"], key="file_uploader")
            if uploaded_file is not None:
                try:
                    df = pd.read_csv(uploaded_file)
                    if "Links" in df.columns or "URL" in df.columns:
                        column_name = "Links" if "Links" in df.columns else "URL"
                        urls = df[column_name].tolist()
                        st.success(f"Found {len(urls)} URLs in the uploaded CSV file.")
                    else:
                        st.error("CSV file must contain a column named 'Links' or 'URL'.")
                except Exception as e:
                    st.error(f"Error reading CSV file: {str(e)}")
        
        # Max URLs Input
        st.header("Settings")
        max_urls = st.number_input("Maximum number of URLs to process (0 = no limit):", min_value=0, value=0, key="max_urls")
        if max_urls == 0:
            max_urls = None
        
        # Extract Button - add a unique key
        if st.button("Extract FAQs", key="extract_button") and urls and firecrawl_api_key and google_api_key:
            try:
                # Create progress placeholders
                st.session_state.progress_placeholder = st.empty()
                st.session_state.status_placeholder = st.empty()
                
                # Initialize extractor with user-provided API keys
                extractor = FAQExtractor(firecrawl_api_key, google_api_key)
                
                # Extract FAQs
                with st.spinner("Extracting FAQs..."):
                    results = extractor.extract_faqs(urls, max_urls=max_urls)
                
                # Create DataFrame from results
                df_results = pd.DataFrame(extractor.data_dict)
                
                # Store results in session state
                st.session_state.results_df = df_results
                st.session_state.missed_urls = extractor.notcollected
                st.session_state.extraction_complete = True
                
                st.success(f"Extraction completed! Processed {len(results['URL'])} URLs.")
            except Exception as e:
                st.error(f"Error during extraction: {str(e)}")
                logger.error(f"Error in Streamlit app: {str(e)}")
        elif urls is None or firecrawl_api_key == '' or google_api_key == '':
            st.warning("Please provide all required inputs: URLs and API keys.")
    
    
    #image_link='data:image/png;base64,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'
    image_link="data:image/png;base64,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"


    st.markdown(
    """
    <style>
    .center {
        display: flex;
        justify-content: center;
    }
    </style>
    """,
    unsafe_allow_html=True
)

    st.markdown(f'<div class="center"><img src={image_link} width="350"></div>', unsafe_allow_html=True)
     # Application name with styling (centered)
    st.markdown("<h1 style='text-align: center; color: #1E88E5;'>FAQ KnowlBase Creator</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Extract FAQs from websites efficiently and accurately</p>", unsafe_allow_html=True)
    

    # Main page content - centered image and title
    # Create a container for the header section
    header_container = st.container()
    
    # with header_container:
    #     # Center the logo
    #     col1, col2, col3 = st.columns([1, 2, 1])
    #     with col2:
    #         # Display GPTfy logo centered
    #         image_link='data:image/png;base64,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'
    #         #image_link="data:image/png;base64,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"
    #         st.image(image_link, width=200)
            
    #         # Application name with styling (centered)
    #         st.markdown("<h1 style='text-align: center; color: #1E88E5;'>FAQ Extractor Tool</h1>", unsafe_allow_html=True)
    #         st.markdown("<p style='text-align: center;'>Extract FAQs from websites efficiently and accurately</p>", unsafe_allow_html=True)
    
    # Only show results if extraction has been completed
    if st.session_state.extraction_complete and st.session_state.results_df is not None:
        # Output filename input
        st.header("Save Results")
        custom_filename = st.text_input("Output CSV filename:", "extracted_faqs.csv", key="custom_filename")
        if not custom_filename.endswith('.csv'):
            custom_filename += '.csv'
            
        # GCP bucket upload option
        gcp_upload = st.checkbox("Upload to GCP Bucket", key="gcp_upload")
        if gcp_upload:
            bucket_name = st.text_input("GCP Bucket Name:", key="bucket_name")
            
        # Save and upload buttons
        col3, col4 = st.columns(2)
        with col3:
            if st.button("Save CSV", key="save_csv_button"):
                # Save results to CSV
                st.session_state.results_df.to_csv(custom_filename, index=False)
                st.success(f"CSV saved as {custom_filename}")
                st.markdown(get_csv_download_link(st.session_state.results_df, custom_filename), unsafe_allow_html=True)
        
        with col4:
            if gcp_upload and st.button("Upload to GCP", key="gcp_upload_button"):
                if not os.path.exists(custom_filename):
                    st.session_state.results_df.to_csv(custom_filename, index=False)
                
                success, message = upload_to_gcp_bucket(
                    custom_filename, 
                    bucket_name, 
                    f"faq_extracts/{custom_filename}"
                )
                
                if success:
                    st.success(message)
                else:
                    st.error(message)
        
        # Display extracted content
        st.header("Extracted FAQs")
        st.dataframe(st.session_state.results_df, key="results_dataframe")
        
        # Display detailed FAQ view
        st.header("Detailed FAQ View")
        results = st.session_state.results_df
        for i in range(len(results["URL"])):
            with st.expander(f"FAQ {i+1}: {results['question'][i][:100]}..."):
                st.write(f"**organisation:** {results['organisation_name'][i]}")
                st.write(f"**question:** {results['question'][i]}")
        
        # Display missed URLs
        st.header('Extraction Failed')
        missed_urls_df = pd.DataFrame({
            'S_No': [i+1 for i in range(len(st.session_state.missed_urls))],
            'Links': st.session_state.missed_urls
        })
        st.dataframe(missed_urls_df, key="missed_urls_dataframe")

if __name__ == "__main__":
    main()