module Jekyll
  class CategoryPageGenerator < Generator
    safe true

    def generate(site)
      if site.layouts.key? 'category'
        site.posts.each do |post|
          post.categories.each do |category|
            category_path = File.join('_site', 'categories', category)
            FileUtils.mkdir_p(category_path)
            category_file = File.join(category_path, 'index.html')
            File.write(category_file, generate_category_page(site, category))
          end
        end
      end
    end

    def generate_category_page(site, category)
      site.pages << CategoryPage.new(site, site.source, 'categories', category)
    end
  end

  class CategoryPage < Page
    def initialize(site, base, dir, category)
      @site = site
      @base = base
      @dir = dir
      @name = 'index.html'

      self.process(@name)
      self.read_yaml(File.join(base, '_layouts'), 'post_with_categories.html')
      self.data['category'] = category
    end
  end
end
