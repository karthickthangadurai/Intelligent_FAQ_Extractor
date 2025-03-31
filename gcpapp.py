import streamlit as st
import pandas as pd
import logging
import os
from dotenv import load_dotenv
import time
import base64
from commonscrape import *
import google.cloud.storage as storage
import random

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

def show_random_text():
    st.write('📚 Knowledge Break: Learn While You Wait! ⏳')
    data = pd.read_csv('KnowlLinksGPTfy.csv',encoding='ISO-8859-1')
    row = random.choice(data.index)
    # Display random text with emojis
    st.session_state.Description = data.loc[row, 'Description']
    st.session_state.Content = data.loc[row, 'Content']
    st.session_state.Links = data.loc[row, 'Links']
    st.write(f"### {st.session_state.Description} 💡😊")
    st.write(f"{st.session_state.Content} 📘✨")
    st.write(f"[Read More]({st.session_state.Links})")

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
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "gptfy-ai-playground-1bc58dbd197f.json"
        
        # Initialize a GCP storage client and upload the file
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
    if 'Description' not in st.session_state:
        st.session_state.Description = None
    if 'Content' not in st.session_state:
        st.session_state.Content = None
    if 'KnowlURL' not in st.session_state:
        st.session_state.KnowlURL = None
    
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

                    ## Show random text while waiting
                    st.header('📚 Knowledge Break: Learn While You Wait! ⏳')
                    data = pd.read_csv('KnowlLinksGPTfy.csv',encoding='ISO-8859-1')
                    row = random.choice(data.index)
                    # Display random text with emojis
                    st.session_state.Description = data.loc[row, 'Description']
                    st.session_state.Content = data.loc[row, 'Content']
                    st.session_state.KnowlURL = data.loc[row, 'KnowlURL']
                    st.write(f"### {st.session_state.Description} 💡😊")
                    st.write(f"{st.session_state.Content} 📘✨")
                    st.write(f"[Read More]({st.session_state.KnowlURL})")

                    results = extractor.extract_faqs(urls, max_urls=max_urls)
                
                # Create DataFrame from results
                df_results = pd.DataFrame(extractor.data_dict)
                
                # Store results in session state
                st.session_state.results_df = df_results
                st.session_state.missed_urls = extractor.notcollected
                st.session_state.extraction_complete = True
                
                st.success(f"Extraction completed! Processed {len(results['URL'])} URLs.")
                if len(extractor.notcollected) == 0: 
                    st.toast('Great Some Data Extracted!', icon='😍')
            except Exception as e:
                st.error(f"Error during extraction: {str(e)}")
                logger.error(f"Error in Streamlit app: {str(e)}")
        elif urls is None or firecrawl_api_key == '' or google_api_key == '':
            st.warning("Please provide all required inputs: URLs and API keys.")
    
    # Display logo
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
    
    # Only show results if extraction has been completed
    if st.session_state.extraction_complete and st.session_state.results_df is not None:

        st.subheader("Extracted FAQs Frame")

        # Display the results DataFrame with row and column selection
        event_df=st.dataframe(st.session_state.results_df, key="results_dataframe",use_container_width=True,
                     hide_index=True,
                     on_select="rerun",
                     selection_mode=["multi-row", "multi-column"],
                     height=200,
                     column_order = ['organisation_name', 'question','answer','links','category','URL'] # Specify the order of columns
                     )
        
        # Display selected rows and columns
        st.subheader("Selected Rows and Columns")
        row_index = event_df.selection.rows
        column_index = event_df.selection.columns
        filtered_df = st.session_state.results_df.loc[row_index,column_index]
        

        if len(row_index) == 0:
            st.warning("Please select at least one row to proceed.")
        elif len(row_index) > 0:
            st.toast(f'Your have selected {len(row_index)}!', icon='😍')
        
        if len(column_index) == 0:
            st.warning("Please select at least one column and row to proceed.")
        elif len(column_index) > 0:
            # Display the filtered DataFrame based on selected rows and columns
            st.dataframe(filtered_df, use_container_width=True,height=200)

            # Output filename input
            st.subheader("Save Results")
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
                    #filtered_df.to_csv(custom_filename, index=False)
                    # st.success(f"CSV saved as {custom_filename}")
                    st.markdown(get_csv_download_link(filtered_df, custom_filename), unsafe_allow_html=True)
            
            with col4:
                if gcp_upload and st.button("Upload to GCP", key="gcp_upload_button"):
                    if not os.path.exists(custom_filename):

                        filtered_df.to_csv(custom_filename, index=False, encoding = 'utf-8-sig')
                    
                    success, message = upload_to_gcp_bucket(
                        custom_filename, 
                        bucket_name, 
                        f"faq_extracts/{custom_filename}"
                    )
                    
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
            
        # Display missed URLs
        st.header('Extraction Failed')
        missed_urls_df = pd.DataFrame({
            'S_No': [i+1 for i in range(len(st.session_state.missed_urls))],
            'Links': st.session_state.missed_urls
        })
        st.dataframe(missed_urls_df, key="missed_urls_dataframe")

if __name__ == "__main__":
    main()
