Locales.each_pair do |id, (filename, path, locale)|

  describe "#{id}" do

    it "is a valid CSL 1.0.1 locale" do
      CSL.validate(path).should == []
    end

    it "has a conventional file name" do
      filename.should match(/^locales-[a-z]{2}(-[A-Z]{2})?\.xml$/)
    end

    it "was successfully parsed" do
      locale.should be_a(CSL::Locale)
    end

    unless locale.nil?
      it "has an info element" do
       locale.should have_info
      end

      it "has a language" do
        locale.language.should_not be_empty
      end

      it "has a region" do
        locale.region.should_not be_empty
      end unless id == 'locales-eu'

      it "its language and region match the filename" do
        locale.to_s.should == id[8,5]
      end

      it "has and info/rights element" do
        locale.info.should have_rights
      end

      it "is licensed under a CC BY-SA license" do
        locale.info.rights.to_s.strip.should ==
          'This work is licensed under a Creative Commons Attribution-ShareAlike 3.0 License'

        locale.info.rights[:license].should == 'http://creativecommons.org/licenses/by-sa/3.0/'
      end
    end

  end
end
